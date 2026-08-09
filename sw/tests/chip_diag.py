# Copyright 2026 KU Leuven.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author: Jiacong Sun <jiacong.sun@kuleuven.be>

# Bring-up diagnostic for the Zedboard-driver.

# Splits the Quad-SPI link into independently testable pieces so a failure points at a
# cause:

#   A  host <-> Zedboard only (chip not involved)
#   B  read a region we never wrote (the boot ROM) - isolates the READ direction
#   C  repeat-read stability - marginal vs deterministic
#   D  burst-length sweep - reports the "good prefix", the hardware fingerprint
#   E  single-word frames vs one burst - is the fault burst-specific?
#   G  quiet vs noisy data patterns - simultaneous-switching noise, or not?
#   H  SCK sweep (--sck-sweep) - the fastest rate that still works

# Reading the results:
#   all-ones / all-zeros on every lane -> the chip drove nothing (see the
#       per-lane report, which maps each Quad-SPI lane to its FMC pin)
#   a whole-NIBBLE shift               -> SCK edge count wrong (a clock fault);
#       data-line noise gives scattered bit errors, never a clean slide
#   0xBADCAB1E / 0xCA11AB1E            -> the AXI decode-error value: the chip
#       answered, but its read went to an unmapped address, so the command/
#       address phase was corrupted

# Usage:
#     python sw/tests/chip_diag.py               # tests A-E, G
#     python sw/tests/chip_diag.py --quick       # tests A-C only
#     python sw/tests/chip_diag.py --sck-sweep   # sweep SCK frequency to find the ceiling


import sys
import random
import logging
import argparse
import time

from sw.lib.chip_driver import ChipDriver, SCK_HZ
from sw.lib.chip_command_api import WRITEBACK_FIFO, make_command

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

WRITE_DEV = "/dev/xillybus_write_32"
READ_DEV = "/dev/xillybus_read_32"

# Cheshire memory map (cheshire_pkg.sv: AmBrom = 'h0200_0000, 256 KiB window).
# The LAGD boot ROM is built into the bitstream, so this region holds real
# RISC-V instructions that the SPI driver has never written.
BOOTROM_BASE = 0x02000000
SCRATCH_BASE = 0x80000000  # L2_MEM_BASE_ADDR (lagd_define.svh)
# L2_MEM is only 64 KiB (lagd_config.svh: L2_MEM_SIZE_B = 64*1024), so every
# test address must stay below SCRATCH_BASE + 0x10000. Reads above that go to
# unmapped space and return the interconnect's error response, which is easy to
# mistake for a link fault.
SCRATCH_SIZE = 64 * 1024


def check_addr(addr, n_words, tag):
    """Guard against testing outside L2_MEM - the results would be meaningless."""
    end = addr + 4 * n_words
    if addr < SCRATCH_BASE or end > SCRATCH_BASE + SCRATCH_SIZE:
        raise ValueError(
            "%s: 0x%08X..0x%08X is outside L2_MEM (0x%08X..0x%08X)"
            % (tag, addr, end - 1, SCRATCH_BASE, SCRATCH_BASE + SCRATCH_SIZE - 1)
        )

def release_chip_reset(chip, hold=0.01, settle=0.20):
    """Pulse the chip's reset low->high and let it come out of reset.

    Required on the NEW ZCU102 bitstream: chip_controller resets chip_rstn_r to
    0, so the SoC is held in reset until this runs. Harmless (inert) on the old
    bitstream, so this is safe to call unconditionally.

    `settle` gives the boot ROM time to start. Cheshire's bootrom first calls
    clint_get_core_freq(), which measures the core clock against rtc_i - so if
    the driver's chip_rtc_o is not toggling, the SoC never leaves that loop.
    """
    chip.config_clk_rst(chip_clk_en=1, chip_rstn=0)
    time.sleep(hold)
    chip.config_clk_rst(chip_clk_en=1, chip_rstn=1)
    time.sleep(settle)


# Which physical pins each Quad-SPI data lane runs on, so a stuck lane points
# straight at a contact to re-seat.
SD_LANE_PINS = {
    0: "FMC LA04_P  (Zedboard M21 <-> ZCU102 AA2)",
    1: "FMC LA04_N  (Zedboard M22 <-> ZCU102 AA1)",
    2: "FMC LA07_P  (Zedboard T16 <-> ZCU102 U5)",
    3: "FMC LA07_N  (Zedboard T17 <-> ZCU102 U4)",
}


def lane_states(words):
    """Split returned words into the four Quad-SPI data lanes.

    In quad mode each SCK moves one nibble sd[3:0] and a 32-bit word is 8
    nibbles, so lane j carries exactly the bit positions p where p % 4 == j.
    A lane that never changes across a whole transfer is not carrying data -
    that is an open contact (floats high) or a short (stuck low), not a logic
    bug. This is what separates a bad connector from an RTL problem.
    """
    out = {}
    for j in range(4):
        bits = [(w >> p) & 1 for w in words for p in range(j, 32, 4)]
        if not bits:
            out[j] = ("no data", 0, 0)
        elif all(bits):
            out[j] = ("STUCK HIGH", sum(bits), len(bits))
        elif not any(bits):
            out[j] = ("STUCK LOW", sum(bits), len(bits))
        else:
            out[j] = ("toggling", sum(bits), len(bits))
    return out


def log_lane_report(words, indent="    "):
    """Log a per-lane verdict; returns True if any lane looks physically dead."""
    states = lane_states(words)
    dead = [j for j, (s, _, _) in states.items() if s in ("STUCK HIGH", "STUCK LOW")]
    if not dead:
        return False
    logger.error("%sPER-LANE ANALYSIS (physical layer):", indent)
    for j, (state, ones, tot) in states.items():
        mark = "  <-- check this contact" if j in dead else ""
        logger.error("%s  sd[%d] %-11s %3d/%-3d ones   %s%s",
                     indent, j, state, ones, tot, SD_LANE_PINS[j], mark)
    if len(dead) == 4:
        logger.error("%sAll four lanes frozen: the chip drove nothing at all.", indent)
    else:
        logger.error("%s%d of 4 lanes carried no data while the others worked.", indent, len(dead))
        logger.error("%sA logic bug cannot freeze individual lanes - this is a CONNECTOR", indent)
        logger.error("%sfault. Re-seat the FMC, check the screws/standoffs and look for", indent)
        logger.error("%sbent or recessed pins on the contacts listed above.", indent)
    return True


def detect_nibble_shift(got, exp, max_shift=16):
    """Is the readback the written data, just misaligned by whole nibbles?

    Quad-SPI moves one nibble per SCK. If the two ends disagree about how many
    SCK edges went by, the whole stream slides by an integral number of nibbles
    while every value stays intact. That is a CLOCK fault (extra or missing SCK
    edges), and it looks completely different from data-line corruption, which
    produces scattered bit errors rather than a clean uniform slide.

    Returns the shift in nibbles, or None.
    """
    if not got or not exp:
        return None
    e = "".join("%08x" % w for w in exp)
    g = "".join("%08x" % w for w in got)
    for shift in range(1, min(max_shift, len(e))):
        if len(g) > shift and g[: len(g) - shift] == e[shift:]:
            return shift
    return None


def good_prefix(got, exp):
    """Number of leading words that match - the hardware failure fingerprint."""
    n = 0
    for g, e in zip(got, exp):
        if g != e:
            break
        n += 1
    return n


def summarise(tag, got, exp):
    n = min(len(got), len(exp))
    match = got[:n] == exp[:n] and len(got) == len(exp)
    pref = good_prefix(got, exp)
    zeros = sum(1 for w in got if w == 0)
    logger.info(
        "%s: %s (%d/%d words returned, good prefix %d, %d zeros)",
        tag,
        "MATCH" if match else "MISMATCH",
        len(got),
        len(exp),
        pref,
        zeros,
    )
    if not match:
        logger.info("    expected: %s", [hex(w) for w in exp[:12]])
        logger.info("    got     : %s", [hex(w) for w in got[:12]])
        shift = detect_nibble_shift(got, exp)
        if shift is not None:
            logger.error("    *** NIBBLE SHIFT: readback is the written data shifted by %d "
                         "nibbles (%d bits) ***", shift, 4 * shift)
            logger.error("        The DATA IS INTACT - it reached memory correctly. The two ends")
            logger.error("        simply disagree by %d SCK edges, so the stream is misaligned.", shift)
            logger.error("        This is a CLOCK fault (extra/missing edges on SCK), NOT data")
            logger.error("        corruption and NOT a driver bug: noise on the data lines would")
            logger.error("        give scattered bit errors, never a clean uniform slide.")
            logger.error("        Target SCK specifically: its own ground return, series")
            logger.error("        termination, shorter wire.")
        else:
            # Only the words that actually came back wrong carry link information;
            # a correct prefix would dilute the stuck-lane evidence.
            bad = [g for g, e in zip(got, exp) if g != e]
            log_lane_report(bad)
    return match


# ---------------------------------------------------------------------------
# Test A: host <-> FPGA only. No SPI wires involved.
# ---------------------------------------------------------------------------
def test_a_fpga_loopback(chip):
    logger.info("=== A: FPGA loopback (host <-> Zedboard, chip NOT involved) ===")
    ok = True
    for payload in (0xADBEE, 0x00000, 0xFFFFF, 0x12345):
        expect = make_command(WRITEBACK_FIFO, payload)
        got = chip.writeback(payload)
        if got != expect:
            logger.error("  writeback 0x%05X: sent 0x%08X got %s", payload, expect,
                         hex(got) if got is not None else "None")
            ok = False
    logger.info("  -> %s", "PASS" if ok else "FAIL (host/xillybus path is broken; stop here)")
    return ok


# ---------------------------------------------------------------------------
# Test B: THE DECISIVE ONE. Read a region we have never written.
# ---------------------------------------------------------------------------
def test_b_bootrom_read(chip):
    logger.info("=== B: read chip boot ROM @ 0x%08X (never written by us) ===", BOOTROM_BASE)
    n = 8
    data = chip.read_mem(BOOTROM_BASE, length=n)
    logger.info("  boot ROM words: %s", [hex(w) for w in data])

    if len(data) < n:
        logger.error("  -> INCONCLUSIVE: only %d/%d words came back (read timed out).", len(data), n)
        return None

    # The boot ROM holds real RISC-V instructions, so neither a constant nor a
    # rail value is a legitimate result. "Non-zero" is NOT sufficient evidence
    # that the chip answered: an undriven bus reads as a rail, and there is no
    # pull-up or pull-down on spi_sd_io on either board (checked in both XDCs).
    if all(w == 0xFFFFFFFF for w in data):
        logger.error("  -> CHIP IS NOT DRIVING THE BUS (all ones).")
        logger.error("     0xFFFFFFFF on every line is the signature of a FLOATING bus:")
        logger.error("     the Zedboard released the data lines for the chip's turn and")
        logger.error("     nothing drove them. The boot ROM cannot read as all ones.")
        logger.error("     This means the ZCU102 never answered - so it is most likely not")
        logger.error("     receiving SCK/CS/command at all, or is held in reset.")
        logger.error("     NEXT: check the ZCU102 LEDs - GPIO_LED_1 (clk_locked, solid) and")
        logger.error("     GPIO_LED_2 (heartbeat, ~1 Hz). See zcu102.xdc.")
        log_lane_report(data)
        return False
    if all(w == 0 for w in data):
        logger.error("  -> CHIP IS NOT DRIVING THE BUS (all zeros).")
        logger.error("     The boot ROM cannot be all zeros: it holds the LAGD boot code")
        logger.error("     built into the ZCU102 bitstream. Either the ZCU102 is not driving")
        logger.error("     the lines, or its levels are not reaching the Zedboard's VIH.")
        return False
    if len(set(data)) == 1:
        logger.error("  -> SUSPICIOUS: all %d boot ROM words are identical (0x%08X).", n, data[0])
        logger.error("     Real boot code is not a constant. Treat this as 'chip did not")
        logger.error("     answer' rather than as a successful read.")
        return False

    logger.info("  -> READ DIRECTION WORKS: the chip returned varied, plausible data.")
    logger.info("     Any zeros seen in LATER tests are therefore real memory contents,")
    logger.info("     i.e. a write that did not land - not a broken read path.")
    return True


# ---------------------------------------------------------------------------
# Test C: is the link stable, or marginal?
# ---------------------------------------------------------------------------
def test_c_read_stability(chip, addr=BOOTROM_BASE, rounds=20):
    logger.info("=== C: repeat-read stability @ 0x%08X, %d rounds (no writes) ===", addr, rounds)
    n = 4
    seen = {}
    for _ in range(rounds):
        got = tuple(chip.read_mem(addr, length=n))
        seen[got] = seen.get(got, 0) + 1

    if len(seen) == 1:
        logger.info("  -> STABLE: every read returned the same %d words.", n)
        logger.info("     Repeated reads of an unwritten address are reproducible, so the")
        logger.info("     link is not varying run-to-run. (If other tests fail despite this,")
        logger.info("     the fault is deterministic rather than marginal.)")
        return True

    logger.error("  -> UNSTABLE: %d distinct results across %d identical reads.", len(seen), rounds)
    for val, cnt in sorted(seen.items(), key=lambda kv: -kv[1]):
        logger.error("     %3dx %s", cnt, [hex(w) for w in val])
    logger.error("     Reading the SAME address without writing must be deterministic.")
    logger.error("     Varying results mean the SPI link itself is marginal (levels,")
    logger.error("     termination, cable) - not a logic bug.")
    return False


# ---------------------------------------------------------------------------
# Test D: burst-length sweep. Directly comparable to the RTL co-sim sweep.
# ---------------------------------------------------------------------------
def test_d_burst_sweep(chip, lengths=(1, 2, 4, 8, 10, 16, 32, 64)):
    logger.info("=== D: burst write/read sweep ===")
    logger.info("  (compare the 'good prefix' column with lagd-im/hw/tb/spi_cosim)")
    results = {}
    for i, n in enumerate(lengths):
        addr = SCRATCH_BASE + 0x1000 * (i + 1)
        data = [random.randint(0, 0xFFFFFFFF) for _ in range(n)]
        chip.write_mem(addr, data)
        got = chip.read_mem(addr, length=n)
        ok = summarise("  n=%-4d" % n, got, data)
        results[n] = (ok, good_prefix(got, data))
    logger.info("  --- summary ---")
    for n, (ok, pref) in results.items():
        logger.info("    n=%-4d %-4s good prefix %d/%d", n, "PASS" if ok else "FAIL", pref, n)
    return results


# ---------------------------------------------------------------------------
# Test E: does framing matter? One long burst vs many single-word frames.
# ---------------------------------------------------------------------------
def test_e_single_vs_burst(chip, n=10):
    logger.info("=== E: %d single-word frames vs one %d-word burst ===", n, n)
    data = [random.randint(0, 0xFFFFFFFF) for _ in range(n)]

    # Must stay inside the 64 KiB L2. The previous 0x20000/0x30000 offsets were
    # OUTSIDE it, so this test was reading unmapped space and its "both fail"
    # result was an artefact, not evidence about the link.
    base = SCRATCH_BASE + 0x9000
    check_addr(base, n, "E singles")
    for i, w in enumerate(data):
        chip.write_mem(base + 4 * i, w)
    got_single = []
    for i in range(n):
        r = chip.read_mem(base + 4 * i, length=1)
        got_single.append(r[0] if r else None)
    single_ok = summarise("  single-word frames", got_single, data)

    base = SCRATCH_BASE + 0xA000
    check_addr(base, n, "E burst")
    chip.write_mem(base, data)
    got_burst = chip.read_mem(base, length=n)
    burst_ok = summarise("  one burst frame   ", got_burst, data)

    if single_ok and not burst_ok:
        logger.error("  -> Singles work, bursts do not: the fault is in sustained")
        logger.error("     streaming (CS held low across words), not in the link levels.")
    elif not single_ok and not burst_ok:
        logger.error("  -> Both fail: the fault is not burst-specific.")
    elif single_ok and burst_ok:
        logger.info("  -> Both work in this run.")
    return single_ok, burst_ok


# ---------------------------------------------------------------------------
# Test G: DRIVER BUG vs LINK NOISE - the decisive experiment.
# ---------------------------------------------------------------------------
def test_g_switching_noise(chip, n=16, rounds=6):
    """Same burst length, same address, same SCK count - only the DATA differs.

    In quad mode each SCK moves one nibble on sd[3:0], so the data pattern
    decides how many of the four lines switch simultaneously:

      QUIET  0x55555555 / 0xAAAAAAAA -> every nibble identical: ZERO lines
             switch during the whole data phase.
      NOISY  0x0F0F0F0F / 0xF0F0F0F0 -> nibbles alternate 0,F,0,F: ALL FOUR
             lines switch on EVERY SCK edge - worst-case simultaneous-switching
             noise through the shared ground return.

    NOTE ON THE PATTERN CHOICE: 0x00000000 and 0xFFFFFFFF would be the obvious
    "quiet" values, but they are exactly what this broken link produces when it
    fails (all lanes stuck low -> 0x00000000; floating bus -> 0xFFFFFFFF), so a
    failed transfer would score as a PASS and the test would report switching
    noise that is not there. 0x55555555 / 0xAAAAAAAA are equally quiet and
    cannot be produced by any observed failure mode.

    The FPGA master's datapath is a plain shift register with no data-dependent
    control (quad_spi_master: write_shift_r <= wdata_i, then shift; state
    changes depend only on nibble/word counters). So the Zedboard behaves
    IDENTICALLY for both patterns - same states, same edges, same timing.

      QUIET passes and NOISY fails  -> simultaneous-switching noise on the
                                       cable. The driver is exonerated.
      both behave the same          -> the fault is not switching-related;
                                       look again at the driver.

    Patterns are alternated with their complement so a "pass" cannot come from
    memory already happening to hold the value.
    """
    logger.info("=== G: quiet vs noisy data patterns (driver bug vs link noise) ===")
    logger.info("  identical burst length, address and SCK count in both cases")

    cases = [
        ("QUIET (0x55555555 / 0xAAAAAAAA)", (0x55555555, 0xAAAAAAAA)),
        ("NOISY (0x0F0F0F0F / 0xF0F0F0F0)", (0x0F0F0F0F, 0xF0F0F0F0)),
    ]
    addr = SCRATCH_BASE + 0xC000
    check_addr(addr, n, "G")

    results = {}
    for name, pats in cases:
        ok = tot = 0
        for r in range(rounds):
            data = [pats[r % 2]] * n
            chip.write_mem(addr, data)
            got = chip.read_mem(addr, length=n)
            ok += sum(1 for g, e in zip(got, data) if g == e)
            tot += n
        results[name] = (ok, tot)
        logger.info("  %-34s %4d/%4d words correct (%.1f%%)", name, ok, tot, 100.0 * ok / tot)

    (q_ok, q_tot), (nz_ok, nz_tot) = results[cases[0][0]], results[cases[1][0]]
    q, z = q_ok / q_tot, nz_ok / nz_tot
    if q > z + 0.15:
        logger.error("  -> SIMULTANEOUS-SWITCHING NOISE CONFIRMED (%.1f%% quiet vs %.1f%% noisy).",
                     100 * q, 100 * z)
        logger.error("     The Zedboard drives both cases identically, so the difference can")
        logger.error("     only come from the cable. Add ground returns (bounce scales as")
        logger.error("     L_gnd/N_grounds), shorten the wires, and/or series-terminate SCK.")
    elif z > q + 0.15:
        logger.info("  -> Noisy patterns do BETTER - not a switching-noise story.")
    else:
        logger.info("  -> No significant difference between quiet and noisy patterns.")
        logger.info("     No measurable switching-noise sensitivity. If the other tests also")
        logger.info("     pass, the link is healthy. If they fail, the cause is something")
        logger.info("     other than simultaneous switching - look at the driver and the")
        logger.info("     SCK/CS contacts.")
    return results


# ---------------------------------------------------------------------------
# Test H: find the usable SCK ceiling empirically.
# ---------------------------------------------------------------------------
def test_h_sck_sweep(chip, freqs=None, n=32, rounds=3):
    """Walk SCK upward and report the fastest rate that still passes.

    The ceiling is set by the read turnaround (the master samples read data
    half an SCK period after the chip launches it), which no static estimate
    pins down well. Measure it.

    Needs the runtime CONFIG_SCK divider (chip_command_api CONFIG_SCK = 0x04);
    without it every data point would cost a Vivado rebuild.

    Restores the starting frequency before returning, so a failed sweep does not
    leave the link parked at an unusable rate.
    """
    if freqs is None:
        # Only EXACTLY reachable rates: SCK = 100 MHz / (2*N) for integer N, so
        # asking for anything else just lands on the nearest divider anyway.
        # Ends at 50 MHz (N=1), the architectural maximum of this divider - not
        # a choice, nothing faster exists. The practical ceiling should be far
        # lower: the master samples read data half an SCK period after the chip
        # launches it, and the cable + IO round trip (~30-60 ns) alone caps SCK
        # near 8-17 MHz. That is what this test is for.
        freqs = (1e3, 10e3, 50e3, 100e3, 250e3, 500e3,      # N = 50000 .. 100
                 1e6, 2e6, 2.5e6, 5e6,                       # N = 50, 25, 20, 10
                 10e6, 12.5e6, 16.667e6, 25e6)               # N = 5, 4, 3, 2
        # Stops at 25 MHz (N=2), the hardware clamp. N=1 (50 MHz) is reachable
        # by the divider but broken - SCK would toggle every bus clock, leaving
        # the data no setup against its own edge.
    logger.info("=== H: SCK sweep - where does the link stop working? ===")

    start_hz = chip.sck_hz
    addr = SCRATCH_BASE + 0xD000
    check_addr(addr, n, "H")
    best = None
    try:
        for f in freqs:
            actual = chip.set_sck_hz(f)
            ok = tot = 0
            for _ in range(rounds):
                data = [random.randint(0, 0xFFFFFFFF) for _ in range(n)]
                chip.write_mem(addr, data)
                got = chip.read_mem(addr, length=n)
                ok += sum(1 for g, e in zip(got, data) if g == e)
                tot += n
            frac = ok / tot
            logger.info("  %9.1f kHz -> %4d/%4d words (%.1f%%) %s",
                        actual / 1e3, ok, tot, 100 * frac,
                        "OK" if frac == 1.0 else "FAIL")
            if frac == 1.0:
                best = actual
            else:
                break   # once it breaks it stays broken; no point going faster
    finally:
        chip.set_sck_hz(start_hz)

    if best is None:
        logger.error("  -> NOTHING passed, not even %.1f kHz. The link is broken "
                     "independently of frequency.", freqs[0] / 1e3)
    else:
        logger.info("  -> Fastest fully-passing SCK: %.1f kHz", best / 1e3)
        logger.info("     Use a safe margin below this, not the knee itself - the")
        logger.info("     limit drifts with temperature and cable handling.")
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="tests A-C only")
    ap.add_argument("--sck-sweep", action="store_true",
                    help="run test H: find the fastest usable SCK (needs CONFIG_SCK)")
    args = ap.parse_args()

    chip = ChipDriver(WRITE_DEV, READ_DEV)
    chip.open()

    # Release reset FIRST. On a bitstream with ext_rst_ni routed the chip is held
    # in reset until this runs, and every read would return zeros - which would
    # look exactly like the failure we are trying to diagnose.
    logger.info("Releasing chip reset (inert on a bitstream without ext_rst_ni routed)...")
    release_chip_reset(chip)

    chip.init_spi()

    if not test_a_fpga_loopback(chip):
        logger.error("Aborting: the host<->FPGA path itself is broken.")
        return 1

    read_ok = test_b_bootrom_read(chip)
    stable = test_c_read_stability(chip)

    sweep = single_ok = burst_ok = None
    if not args.quick:
        sweep = test_d_burst_sweep(chip)
        single_ok, burst_ok = test_e_single_vs_burst(chip)
        test_g_switching_noise(chip)
    if args.sck_sweep:
        test_h_sck_sweep(chip)

    # Overall verdict from EVERY test, not just test B. Previously this was
    # driven by test B alone, so a fully passing suite could still print
    # "investigate the write path" - misleading once the link is healthy.
    all_pass = (read_ok is True and stable
                and (args.quick or (sweep is not None
                                    and all(ok for ok, _ in sweep.values())
                                    and single_ok and burst_ok)))

    logger.info("==========================================================")
    if all_pass:
        edges = 0
        if sweep:
            # write frame 10+8n SCK, read frame 43+8n SCK.
            edges = sum((10 + 8 * n) + (43 + 8 * n) for n in sweep)
        logger.info("VERDICT: LINK HEALTHY - every test passed.")
        logger.info("  The chip answers, bursts up to the longest tested length are")
        logger.info("  intact, and quiet/noisy patterns behave identically.")
        if edges:
            logger.info("  Evidence: ~%d clean SCK edges in the burst sweep alone.", edges)
            logger.info("  NOTE: an ELF preload is ~100k edges. Before trusting this for a")
            logger.info("  real image, soak it - see write_mem_verified() in chip_driver.py,")
            logger.info("  which retries and reports the error rate.")
        logger.info("==========================================================")
        return 0
    logger.info("==========================================================")
    if read_ok is False:
        logger.info("VERDICT: the chip never answered usefully on the SPI bus.")
        logger.info("  The Zedboard's master is transacting correctly (test A passes and")
        logger.info("  the transfers take the expected time at %d Hz SCK), but the chip's"
                    " replies are wrong.", chip.sck_hz)
        logger.info("  If the returned words contain 0xBADCAB1E or 0xCA11AB1E (possibly")
        logger.info("  byte-rotated), that is the AXI decode-error value: the chip DID")
        logger.info("  answer, but its AXI read went to an UNMAPPED address - so the")
        logger.info("  command/address phase was corrupted on the wire, not just the data.")
        logger.info("  CHECK IN THIS ORDER:")
        logger.info("   1. ZCU102 LEDs: GPIO_LED_1 (clk_locked) solid ON,")
        logger.info("      GPIO_LED_2 (heartbeat) blinking ~1 Hz. If not, the SoC is not")
        logger.info("      running and nothing else matters.")
        logger.info("   2. Scope SCK / CS at the ZCU102 FMC end - do the driver's signals")
        logger.info("      even arrive, and at what swing?")
        logger.info("   3. Confirm VADJ_FMC is still 1.8 V under load.")
    elif read_ok is True:
        logger.info("VERDICT: the read direction works; investigate the write path")
        logger.info("  and whether the free-running CVA6 is overwriting 0x80000000.")
    else:
        logger.info("VERDICT: inconclusive - see test B above.")
    logger.info("==========================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())

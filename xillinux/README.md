# Xillinux OS Setup

This folder is a placeholder for all the settings required to deploy the xillinux on the FPGA, such as the Xillinux image, network scripts, scripts that are useful after the Xillinux is set up on the FPGA. The folder structure follows the same structure as in the Linux OS.

You can find the Xillinux image in the release page. The image contains a built-in Xillinux OS (a Ubuntu OS). Commonly used python packages (please check the [sw/README.md](../sw/README.md) for more details) and OpenOCD have been installed. The OS has the following behaviors:

- It is a standalone tiny Linux OS, but without GUI and VNC service.
- The network automatically works once you connect an ethernet cable to the Zedboard. Remote SSH works.
- The default logged user is `root`. There is another username `mlab_user` without root priviledge.
- A train game is installed to test if the OS works. Try in the terminal: `sl`.
- An example Zedboard bitstream file is placed under `/mnt/pl_sd/xillydemo.bit`. This bitstream enables two LEDs (LD4 and LD8) flash per second.
- **Note**: The system date is always incorrect whenever it reboots, because it never syncs with the internet date.

## How to create your Xillinux OS on Zedboard?

Please download a portable version of [DiskGenius](https://www.diskgenius.com/download.php) on your PERSONAL computer. Do not use your campus computer because you do not have full administration.

In DiskGenius, restore the image to your new SD card using the image in the release. When it finishes, please plug it in the Zedboard. You should see:

- Two LEDs flash per second.
- The screen is on.
- The UART works if you connect the Zedboard to your PC by UART and open a UART interface (e.g., create a new serial session within [MobaXterm](https://mobaxterm.mobatek.net/download-home-edition.html) on baudrate 115200).

Ensure the physical lock (or tab) of the SD card is unlocked (otherwise the boot does not work since the SD card is read-only). If you cannot find where the physical lock is, please check the `Way 1: Manual Unlock` section at [this page](https://www.cleverfiles.com/howto/unlock-sd-card.html).

Boot the Zedboard and log in via uart. We need to configure the following things:

**Update the system hostname:** you need to change the system name to avoid it collides with other OS copies. The default name is `lagdboard`. Suppose the new hostname is `my-env`:

- Please run the commands below:

```[bash]
sudo hostnamectl set-hostname my-env
```

- We also need to rename the network host file. Open the host file in vim by `vim /etc/hosts`. Look for the line `127.0.0.1    lagdboard` and change it to:

```[bash]
127.0.0.1    my-env
```

- Reboot the FPGA to apply the change.

**Configure the internet**: Since the FPGA is usually used within a campus network which has firewalls and requests authorization first, it is needed to set up the internet with proper campus authorization.

- Check the Zedboard MAC address `cloned-mac-address` in [etc/NetworkManager/system-connections/eth0](etc/NetworkManager/system-connections/eth0) and verify its uniqueness in your local network (no local conflict). If the MAC is already in use, change it. This can also be found in the xillybus manual at [here](https://xillybus.com/downloads/doc/xillybus_getting_started_zynq.pdf).

- Enable the `wpa_supplicant` service with `systemctl enable wpa_supplicant`.

- (Optional) Run the `fixboottime.sh`. This shortens the timeout for the network interface.

- Run the `cd /etc/wpa_supplicant/ && source wpa_supplicant_setup.sh` and enter your ESAT password and username when prompted. If you are not KU Leuven/ESAT user, please check how to set up authorization for your network.

- Check the date&time set in `/root/fixnetworking.sh` is more or less up to date, e.g., to a few hours before the current time. Then run `/root/fixnetworking.sh`.

- (Optional) Add the contents of the `/root/crontab` file to the root `crontab` (run `crontab -e` and paste the constants). This fixes networking every time you re-boot your Zedboard.

- If you face connectivity issues each time you reboot your Zedboard, add the following lines in crontab: `@reboot service networking start` and `@reboot service shh start` as well.

- Run the following two commands to avoid stalling the boot if your authorization (e.g., password) may expires one day. Then, please re-set up the connection by rerunning `/etc/wpa_supplicant/wpa_supplicant_setup.sh` and `/root/fixnetworking.sh`.

```bash
sudo systemctl disable NetworkManager-wait-online.service
sudo systemctl mask NetworkManager-wait-online.service
```

**Update the IP email script**: Once you connect the FPGA to ethernet, it will send an email to notify its latest IP address. Please update the script so that it matches with your new own email address (a copy of the same script is put under current github folder):

- Open the script by `vim /usr/local/bin/report_ip.sh`

- Replace `lagdboard` with your new name `my-env`, and put your own email address in.

**Note**: if the network does not work automatically, please check the script `/root/fixnetworking.sh` and `/root/fixboottime.sh`.

**Mount the SD card partition (`/dev/mmcblk0p1`) to `/mnt/pl_sd`**: This is the partition that the PL (programmable logic) reads the FPGA bitstream from. It is put within `/root/.bashrc` and it is executed **automatically** on boot (because `root` is the default user), so you normally do not need to run it by hand.

The FPGA bitstream `xillydemo.bit` should be placed under this mounted folder (`/mnt/pl_sd/xillydemo.bit`) so that it is loaded into the PL.

**Mounts a remote server directory onto the local FPGA filesystem over `sshfs`**: This is to enable the FPGA can directly access scripts hosted on other servers, so that it's not needed to manually copy each time. To do this, please run `source Workspace/mount_workspace.sh`. It opens an SSH tunnel through the campus gateway and then mounts the remote path through that tunnel with read-only permission.

Before running it, edit the configuration block at the top of the [`mount_workspace.sh`](Workspace/mount_workspace.sh) to match your setup.

To kill a mount, please run `fusermount -u /PATH/ON/LOCAL/FPGA/`.


## What if I want to the date to be correct?

The issue is that the Zedboard does not run-time clock when it is powered off. However, we can sync the date manually each time it is powered on.

Please follow the steps below:

- Open `vim /etc/chrony/chrony.conf`
- Locate the line `pool 2.debian.pool.ntp.org iburst #offline` (should be on line 20), and change it to:

```[bach]
server 2.debian.pool.ntp.org iburst
```

- Enter the command `chronyd -d` in the terminal. If it shows ` System clock was stepped by ... seconds` without errors, stop it by pressing `Ctrl+C`.
- Now we can sync the time by entering the commands below:

```[bash]
sudo invoke-rc.d chrony restart
date
chronyc tracking
```

### Why cannot I run `sudo apt update`?

The Xillinux OS is using an outdated Ubuntu. So, to update packages, we need to relink the ubuntu's location so that it correctly accesses the one that correponds to our current OS.

Run the commands below:

```[bash]
cp -f /etc/apt/sources.list /etc/apt/sources.list.bak

cat << 'EOF' > /etc/apt/sources.list
deb http://ports.ubuntu.com/ubuntu-ports/ xenial main restricted universe multiverse
deb http://ports.ubuntu.com/ubuntu-ports/ xenial-updates main restricted universe multiverse
deb http://ports.ubuntu.com/ubuntu-ports/ xenial-security main restricted universe multiverse
EOF

sudo apt update
```

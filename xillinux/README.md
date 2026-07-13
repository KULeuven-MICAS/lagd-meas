# Xillinux OS Setup

Author: Jiacong Sun

Date: 2026/07/13

This folder is a placeholder for all the settings required to deploy the xillinux on the FPGA, such as the Xillinux image, network scripts, scripts that are useful after the Xillinux is set up on the FPGA.

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
- The UART works if you connect the Zedboard to your PC by UART and open a UART interface (e.g., create a new serial session within [MobaXterm](https://mobaxterm.mobatek.net/download-home-edition.html) with speed 115200).

Keep the UART interface open, since we need to configure the following things:

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

**Update the IP email script**: Once you connect the FPGA to ethernet, it will send an email to notify its latest IP address. Please update the script so that it matches with your new own email address (a copy of the same script is put under current github folder):

- Open the script by `vim /usr/local/bin/report_ip.sh`

- Replace `lagdboard` with your new name `my-env`, and put your own email address in.


**Note**: if the network does not work automatically, please check the script `/root/fixnetworking.sh` and `/root/fixboottime.sh`.

## Scripts in this folder

This folder ships a few helper scripts. Below is what each one does and how it is meant to be used.

### `mount_pl_sd.sh`

Mounts the SD card partition (`/dev/mmcblk0p1`) to `/mnt/pl_sd`. This is the partition that the PL (programmable logic) reads the FPGA bitstream from, and it is executed **automatically** on boot, so you normally do not need to run it by hand.

The FPGA bitstream `xillydemo.bit` should be placed under this mounted folder (`/mnt/pl_sd/xillydemo.bit`) so that it is loaded into the PL.

### `mount_workspace.sh`

Mounts a remote server directory onto the local FPGA filesystem over `sshfs`, so that the FPGA can access files hosted on other servers. It first opens an SSH tunnel through the campus gateway and then mounts the remote path through that tunnel.

Before running it, edit the configuration block at the top of the script to match your setup:

- `PORT` — the local port used for the SSH tunnel.
- `UNAME` — your username on the campus SSH gateway / remote server.
- `REMOTE_PATH` — the directory on the remote server you want to access.
- `LOCAL_DIR` — the local directory on the FPGA where the remote files are mounted.

You will be prompted for your server password (once to open the tunnel, once to mount).

### `report_ip.sh`

Reports the IP address of the ZedBoard by email after it boots and connects to the campus network. See the [setup section above](#how-to-create-your-xillinux-os-on-zedboard) for how to update it under `/usr/local/bin/report_ip.sh` (it is automatically triggered on reboot via `crontab`). Remember to change the email address to your own.

## Others

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

# Xillinux OS Setup

Author: Jiacong Sun

Date: 2026/07/13

This folder is a placeholder for all the settings required to deploy the xillinux on the FPGA, such as the Xillinux image, network scripts, scripts that are useful after the Xillinux is set up on the FPGA.

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

**Update the IP email script**: Once you connect the FPGA to ethernet, it will send an email to notify its latest IP address. Please update the script so that it matches with your new own email address:

- Open the script by `vim /usr/local/bin/report_ip.sh`

- Replace `lagdboard` with your new name `my-env`, and put your own email address in.


**Note**: if the network does not work automatically, please check the script `/root/fixnetworking.sh` and `/root/fixboottime.sh`.

## Others

### How to run `sudo apt update`?

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

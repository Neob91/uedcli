#!/bin/bash
set -e
B=https://dl.winehq.org/wine-builds/debian
cp -a /root/dtools-rootfs /root/wine10-rootfs
cd /root
for f in wine-stable_10.0.0.0~bookworm-1_amd64.deb wine-stable-amd64_10.0.0.0~bookworm-1_amd64.deb wine-stable-i386_10.0.0.0~bookworm-1_i386.deb; do
  curl -sSL -o "/root/$f" "$B/pool/main/w/wine/$f"
done
for f in wine-stable_10.0.0.0~bookworm-1_amd64 wine-stable-amd64_10.0.0.0~bookworm-1_amd64 wine-stable-i386_10.0.0.0~bookworm-1_i386; do
  dpkg-deb -x /root/$f.deb /root/wine10-rootfs   # rootfs (loader + .so)
  dpkg-deb -x /root/$f.deb /                       # real fs (PE dlls for guest open())
done
ln -sfn /root/wine10-rootfs ~/.local/share/fex-emu/RootFS/wine10
cp -L /etc/resolv.conf /root/wine10-rootfs/etc/resolv.conf 2>/dev/null || true
echo '{ "Config": { "RootFS": "wine10" } }' > /root/.config/fex-emu/Config.json
echo "SETUP_DONE wine=$(FEXBash -c '/opt/wine-stable/bin/wine --version' 2>/dev/null)"

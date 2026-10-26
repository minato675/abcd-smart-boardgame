#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root (for example: sudo scripts/install.sh)." >&2
    exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir="$project_dir/build-release"
config_dir=/etc/rpi-cabinet-controller
libexec_dir=/usr/local/libexec/rpi-cabinet-controller

cmake -S "$project_dir" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_TESTING=ON
cmake --build "$build_dir" --parallel
ctest --test-dir "$build_dir" --output-on-failure
cmake --install "$build_dir" --prefix /usr/local

install -d -m 0750 "$config_dir"
install -d -m 0755 "$libexec_dir"
install -m 0755 "$project_dir/scripts/setup-rfcomm.sh" \
    "$libexec_dir/setup-rfcomm.sh"
install -m 0644 "$project_dir/systemd/rpi-cabinet-controller.service" \
    /etc/systemd/system/rpi-cabinet-controller.service
install -m 0644 "$project_dir/systemd/rpi-cabinet-controller.sysusers" \
    /usr/lib/sysusers.d/rpi-cabinet-controller.conf
install -m 0644 "$project_dir/utils/cr100emur/udev/70-cr100emur.rules" \
    /etc/udev/rules.d/70-cr100emur.rules

systemd-sysusers /usr/lib/sysusers.d/rpi-cabinet-controller.conf
if ! id cabinet-controller >/dev/null 2>&1; then
    echo "Could not create cabinet-controller service account." >&2
    exit 1
fi
usermod -a -G dialout cabinet-controller
chown root:cabinet-controller "$config_dir"

if [ ! -e "$config_dir/controller.conf" ]; then
    install -m 0640 -o root -g cabinet-controller \
        "$project_dir/config/controller.conf.example" \
        "$config_dir/controller.conf"
    echo "Created $config_dir/controller.conf; edit it before starting the service."
else
    echo "Preserved existing $config_dir/controller.conf."
fi

chown root:cabinet-controller "$config_dir/controller.conf"
chmod 0640 "$config_dir/controller.conf"
udevadm control --reload-rules
systemctl daemon-reload
systemctl enable rpi-cabinet-controller.service

echo "Installation complete. Validate configuration with:"
echo "  sudo -u cabinet-controller /usr/local/bin/rpi-cabinet-controller --check-config"
echo "Then start with: systemctl start rpi-cabinet-controller"

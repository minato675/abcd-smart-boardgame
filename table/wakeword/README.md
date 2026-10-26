# WakeWordModule

This directory contains the single-room wake-word service described in `WAKEWORD_MODULE_IMPLEMENTATION.md`.

The five required ONNX artifacts are checked into `models/` and hash-checked at startup. They remain quality-unverified; production validation fails closed until a trusted, quality-passed deployment manifest exists.

Bootstrap the clone, install the pinned dependencies, install the package, and validate the bundled configuration:

```bash
./scripts/bootstrap.sh
```

Validate the development artifact configuration:

```bash
.venv/bin/python -m wakeword_module.manifest \
  --config config/development.yaml --allow-unverified
```

Run an offline replay without using `Model.predict_clip()`:

```bash
.venv/bin/python -m wakeword_module.replay \
  --config config/development.yaml --warmup-frames 25
```

Run the live service with detailed logs:

```bash
WAKEWORD_ALLOW_UNVERIFIED_MODELS=true .venv/bin/python \
  -m wakeword_module --config config/development.yaml --log-level DEBUG
```

Run the Jetson shadow service with the USB microphone:

~~~bash
./scripts/run-shadow.sh
~~~

The launcher selects the first USB PulseAudio capture source and requires
`config/shadow.yaml` to use `audio.device: pulse`. It loads and exports
`SSAFY` from `~/.config/wakeword/ssafy.env` (mode 600) or ignored `.env.shadow`.
Keep the credential value outside the repository; no per-launch export is needed.

Logs are emitted as JSON to stderr. `DEBUG` includes one inference-score record
per processed audio frame; `INFO` shows lifecycle and detection events only.

The shadow configuration enables `continue_listening_after_detection`: wakeword
events are published, then capture is re-armed automatically. An explicit
`stop-listen` command is required to return the module to `idle`.

The service never records or persists microphone audio. Offline replay accepts externally supplied WAV fixtures; they are not required for live operation and do not establish production quality.

## Fresh clone prerequisites

The bootstrap script requires Python 3.11+ and a working virtual-environment
module. Live capture also requires PortAudio and an MQTT broker. On Ubuntu,
install the host packages once:

```bash
sudo apt-get install python3.11-venv libportaudio2 mosquitto
sudo systemctl enable --now mosquitto
```

Then run `./scripts/bootstrap.sh` from this directory. The default
`config/development.yaml` uses `localhost:1883`, the default audio device,
and unverified-model mode for development. Copy it to the ignored
`config/shadow.yaml` to customize a test room or broker; keep credentials in
environment variables.

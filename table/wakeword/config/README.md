# Configuration

`development.yaml` is the committed, safe default configuration for a fresh
clone. It uses the local MQTT broker and the default audio input device.

The model paths and SHA-256 digests are part of the checked-in configuration.
The file contains no credentials or private endpoints.

## Local shadow configuration

Create a local shadow copy when testing against another broker:

```bash
cp config/development.yaml config/shadow.yaml
```

Edit `config/shadow.yaml` for the room, device, and broker. Keep MQTT username
and password values in environment variables named by `username_env` and
`password_env`; do not put their values in YAML.

For the Jetson USB microphone, set `audio.device: pulse` in the shadow file.
The launcher automatically loads and exports `SSAFY` from a mode-600 user
`~/.config/wakeword/ssafy.env` (mode 600) or ignored `.env.shadow`; no per-launch export is needed.

## Production

Production requires a deployment manifest, trusted manifest digest, verified
model-quality evidence, TLS, and persistent state paths. Keep those inputs

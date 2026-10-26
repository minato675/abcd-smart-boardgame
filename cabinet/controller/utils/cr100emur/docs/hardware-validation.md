# Hardware validation

Validation date: 2026-07-24 (Asia/Seoul)

## Connected device

```text
USB VID:PID       10c4:ea60
USB manufacturer  Silicon Labs
USB product       CP2102 USB to UART Bridge Controller
USB serial        0001
Kernel driver     cp210x
TTY               /dev/ttyUSB0
Stable SDK node   /dev/cr100emur
Serial settings   9600 8-N-1, no flow control
```

The installed `udev/70-cr100emur.rules` rule created `/dev/cr100emur` and
applied the `uaccess` ACL successfully.

## Raw card scan

Command:

```sh
build/cr100-dump --baud 9600
```

Captured bytes:

```text
00000000  02                                                |.|
00000001  36                                                |6|
00000002  38                                                |8|
00000003  30                                                |0|
00000004  30                                                |0|
00000005  36                                                |6|
00000006  39                                                |9|
00000007  44                                                |D|
00000008  44                                                |D|
00000009  32                                                |2|
0000000a  42                                                |B|
0000000b  0d                                                |.|
0000000c  0a                                                |.|
0000000d  03                                                |.|
Captured 14 byte(s).
```

This proves the wire frame is:

```text
STX + 10 ASCII hexadecimal UID characters + CR + LF + ETX
```

The bytes arrived in separate reads, validating that the incremental parser
handles arbitrary USB/serial fragmentation.

## SDK card scan

Command:

```sh
build/cr100-read --count 1 --format json
```

Output:

```json
{"uid":"680069DD2B","value":446683536683,"bytes":[104,0,105,221,43]}
```

The raw payload, parsed hexadecimal UID, byte representation, and unsigned
40-bit value agree:

```text
ASCII payload  680069DD2B
UID bytes      68 00 69 DD 2B
Integer        0x680069DD2B = 446683536683
```

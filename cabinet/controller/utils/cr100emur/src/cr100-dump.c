#include "cr100emur.h"

#include <ctype.h>
#include <errno.h>
#include <getopt.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DUMP_BUFFER_SIZE 256

static void usage(FILE *stream, const char *program)
{
    fprintf(stream,
            "Usage: %s [OPTIONS]\n"
            "Capture unparsed bytes from a CR-100EMUR card scan.\n\n"
            "  -d, --device PATH     serial device (default: auto-detect)\n"
            "  -b, --baud RATE       serial rate (default: %d)\n"
            "  -t, --timeout MS      initial wait for data (default: 10000)\n"
            "  -s, --settle MS       stop after this idle time (default: 100)\n"
            "  -h, --help            show this help\n",
            program,
            CR100EMUR_DEFAULT_BAUD);
}

static int parse_unsigned(const char *text, unsigned long *value)
{
    char *end;

    errno = 0;
    *value = strtoul(text, &end, 10);
    if (errno != 0 || *text == '\0' || *end != '\0') {
        return -1;
    }
    return 0;
}

static void dump_bytes(const uint8_t *data, size_t length, size_t *offset)
{
    size_t position;

    for (position = 0; position < length; position += 16) {
        size_t line_length = length - position;
        size_t index;

        if (line_length > 16) {
            line_length = 16;
        }
        printf("%08zx  ", *offset + position);
        for (index = 0; index < 16; ++index) {
            if (index < line_length) {
                printf("%02x ", data[position + index]);
            } else {
                fputs("   ", stdout);
            }
            if (index == 7) {
                putchar(' ');
            }
        }
        fputs(" |", stdout);
        for (index = 0; index < line_length; ++index) {
            unsigned char byte = data[position + index];
            putchar(isprint(byte) ? byte : '.');
        }
        puts("|");
    }
    *offset += length;
    fflush(stdout);
}

int main(int argc, char **argv)
{
    static const struct option long_options[] = {
        {"device", required_argument, NULL, 'd'},
        {"baud", required_argument, NULL, 'b'},
        {"timeout", required_argument, NULL, 't'},
        {"settle", required_argument, NULL, 's'},
        {"help", no_argument, NULL, 'h'},
        {NULL, 0, NULL, 0}
    };
    const char *device = NULL;
    unsigned int baud = CR100EMUR_DEFAULT_BAUD;
    int timeout_ms = 10000;
    int settle_ms = 100;
    int option;
    cr100_handle *reader;
    uint8_t buffer[DUMP_BUFFER_SIZE];
    size_t offset = 0;
    int received_data = 0;
    int result;

    while ((option = getopt_long(argc,
                                 argv,
                                 "d:b:t:s:h",
                                 long_options,
                                 NULL)) != -1) {
        unsigned long value;

        switch (option) {
        case 'd':
            device = optarg;
            break;
        case 'b':
            if (parse_unsigned(optarg, &value) != 0 || value > 115200) {
                fprintf(stderr, "Invalid baud rate: %s\n", optarg);
                return 2;
            }
            baud = (unsigned int)value;
            break;
        case 't':
            if (parse_unsigned(optarg, &value) != 0 ||
                value > 2147483647UL) {
                fprintf(stderr, "Invalid timeout: %s\n", optarg);
                return 2;
            }
            timeout_ms = (int)value;
            break;
        case 's':
            if (parse_unsigned(optarg, &value) != 0 ||
                value > 2147483647UL) {
                fprintf(stderr, "Invalid settle time: %s\n", optarg);
                return 2;
            }
            settle_ms = (int)value;
            break;
        case 'h':
            usage(stdout, argv[0]);
            return 0;
        default:
            usage(stderr, argv[0]);
            return 2;
        }
    }

    if (optind != argc) {
        usage(stderr, argv[0]);
        return 2;
    }

    result = cr100_open(&reader, device, baud);
    if (result != CR100_OK) {
        fprintf(stderr, "cr100-dump: %s", cr100_strerror(result));
        if (result == CR100_ERR_ACCESS || result == CR100_ERR_IO) {
            fprintf(stderr, ": %s", strerror(errno));
        }
        fputc('\n', stderr);
        if (result == CR100_ERR_ACCESS) {
            fprintf(stderr,
                    "Install udev/70-cr100emur.rules, then reconnect the "
                    "reader.\n");
        }
        return 1;
    }

    fprintf(stderr,
            "Listening on %s at %u baud; present one card now.\n",
            cr100_device_path(reader),
            baud);

    for (;;) {
        size_t bytes_read;
        int wait_ms = received_data ? settle_ms : timeout_ms;

        result = cr100_read_raw(reader,
                                buffer,
                                sizeof(buffer),
                                &bytes_read,
                                wait_ms);
        if (result == CR100_TIMEOUT) {
            break;
        }
        if (result != CR100_OK) {
            fprintf(stderr, "cr100-dump: %s\n", cr100_strerror(result));
            cr100_close(reader);
            return 1;
        }
        received_data = 1;
        dump_bytes(buffer, bytes_read, &offset);
    }

    cr100_close(reader);
    if (!received_data) {
        fprintf(stderr,
                "cr100-dump: no bytes received within %d ms\n",
                timeout_ms);
        return 3;
    }
    fprintf(stderr, "Captured %zu byte(s).\n", offset);
    return 0;
}


#include "cr100emur.h"

#include <errno.h>
#include <getopt.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested = 0;

enum output_format {
    FORMAT_HEX,
    FORMAT_DECIMAL,
    FORMAT_JSON,
    FORMAT_BYTES
};

static void request_stop(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static void usage(FILE *stream, const char *program)
{
    fprintf(stream,
            "Usage: %s [OPTIONS]\n"
            "Read 125 kHz EM card UIDs from a CR-100EMUR.\n\n"
            "  -d, --device PATH     serial device (default: auto-detect)\n"
            "  -b, --baud RATE       serial rate (default: %d)\n"
            "  -n, --count N         stop after N cards (default: unlimited)\n"
            "  -t, --timeout MS      per-card timeout; -1 waits forever\n"
            "  -f, --format FORMAT   hex, decimal, json, or bytes\n"
            "  -l, --list            locate the reader and report access\n"
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

static int parse_format(const char *text, enum output_format *format)
{
    if (strcmp(text, "hex") == 0) {
        *format = FORMAT_HEX;
    } else if (strcmp(text, "decimal") == 0) {
        *format = FORMAT_DECIMAL;
    } else if (strcmp(text, "json") == 0) {
        *format = FORMAT_JSON;
    } else if (strcmp(text, "bytes") == 0) {
        *format = FORMAT_BYTES;
    } else {
        return -1;
    }
    return 0;
}

static void print_card(const cr100_card *card, enum output_format format)
{
    size_t index;

    switch (format) {
    case FORMAT_HEX:
        puts(card->hex);
        break;
    case FORMAT_DECIMAL:
        printf("%" PRIu64 "\n", card->value);
        break;
    case FORMAT_JSON:
        printf("{\"uid\":\"%s\",\"value\":%" PRIu64 ",\"bytes\":[",
               card->hex,
               card->value);
        for (index = 0; index < CR100EMUR_UID_BYTES; ++index) {
            printf("%s%u", index == 0 ? "" : ",", card->uid[index]);
        }
        puts("]}");
        break;
    case FORMAT_BYTES:
        for (index = 0; index < CR100EMUR_UID_BYTES; ++index) {
            printf("%s%02X", index == 0 ? "" : ":", card->uid[index]);
        }
        putchar('\n');
        break;
    }
    fflush(stdout);
}

static int list_reader(void)
{
    char path[512];
    int result = cr100_find_device(path, sizeof(path));

    if (result != CR100_OK) {
        fprintf(stderr, "%s\n", cr100_strerror(result));
        return 1;
    }

    printf("%s\taccess=%s\n",
           path,
           access(path, R_OK) == 0 ? "yes" : "no");
    if (access(path, R_OK) != 0) {
        fprintf(stderr,
                "Install udev/70-cr100emur.rules, then reconnect the reader.\n");
        return 2;
    }
    return 0;
}

int main(int argc, char **argv)
{
    static const struct option long_options[] = {
        {"device", required_argument, NULL, 'd'},
        {"baud", required_argument, NULL, 'b'},
        {"count", required_argument, NULL, 'n'},
        {"timeout", required_argument, NULL, 't'},
        {"format", required_argument, NULL, 'f'},
        {"list", no_argument, NULL, 'l'},
        {"help", no_argument, NULL, 'h'},
        {NULL, 0, NULL, 0}
    };
    const char *device = NULL;
    unsigned int baud = CR100EMUR_DEFAULT_BAUD;
    unsigned long count = 0;
    int timeout_ms = -1;
    enum output_format format = FORMAT_HEX;
    int should_list = 0;
    int option;
    cr100_handle *reader;
    unsigned long cards_read;
    int result;
    struct sigaction action;

    while ((option = getopt_long(argc,
                                 argv,
                                 "d:b:n:t:f:lh",
                                 long_options,
                                 NULL)) != -1) {
        unsigned long value;

        switch (option) {
        case 'd':
            device = optarg;
            break;
        case 'b':
            if (parse_unsigned(optarg, &value) != 0 ||
                value > 115200) {
                fprintf(stderr, "Invalid baud rate: %s\n", optarg);
                return 2;
            }
            baud = (unsigned int)value;
            break;
        case 'n':
            if (parse_unsigned(optarg, &count) != 0) {
                fprintf(stderr, "Invalid card count: %s\n", optarg);
                return 2;
            }
            break;
        case 't':
            if (strcmp(optarg, "-1") == 0) {
                timeout_ms = -1;
            } else if (parse_unsigned(optarg, &value) != 0 ||
                       value > 2147483647UL) {
                fprintf(stderr, "Invalid timeout: %s\n", optarg);
                return 2;
            } else {
                timeout_ms = (int)value;
            }
            break;
        case 'f':
            if (parse_format(optarg, &format) != 0) {
                fprintf(stderr, "Invalid output format: %s\n", optarg);
                return 2;
            }
            break;
        case 'l':
            should_list = 1;
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
    if (should_list) {
        return list_reader();
    }

    result = cr100_open(&reader, device, baud);
    if (result != CR100_OK) {
        fprintf(stderr, "cr100-read: %s", cr100_strerror(result));
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

    memset(&action, 0, sizeof(action));
    action.sa_handler = request_stop;
    sigemptyset(&action.sa_mask);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGTERM, &action, NULL);

    cards_read = 0;
    while (!stop_requested && (count == 0 || cards_read < count)) {
        cr100_card card;
        int effective_timeout = timeout_ms;

        if (timeout_ms < 0 && count == 0) {
            effective_timeout = 500;
        }
        result = cr100_read_card(reader, &card, effective_timeout);
        if (result == CR100_TIMEOUT) {
            if (timeout_ms >= 0) {
                fprintf(stderr, "cr100-read: %s\n", cr100_strerror(result));
                cr100_close(reader);
                return 3;
            }
            continue;
        }
        if (result != CR100_OK) {
            fprintf(stderr, "cr100-read: %s\n", cr100_strerror(result));
            cr100_close(reader);
            return 1;
        }
        print_card(&card, format);
        ++cards_read;
    }

    cr100_close(reader);
    return 0;
}


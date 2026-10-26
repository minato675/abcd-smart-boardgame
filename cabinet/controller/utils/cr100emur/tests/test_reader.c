#include "cr100emur.h"

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define EXPECT(condition)                                                     \
    do {                                                                      \
        if (!(condition)) {                                                   \
            fprintf(stderr,                                                   \
                    "%s:%d: expectation failed: %s (errno=%d)\n",             \
                    __FILE__,                                                 \
                    __LINE__,                                                 \
                    #condition,                                               \
                    errno);                                                   \
            result = 1;                                                       \
            goto cleanup;                                                     \
        }                                                                     \
    } while (0)

struct callback_context {
    cr100_card cards[4];
    size_t count;
};

static void collect_card(const cr100_card *card, void *user_data)
{
    struct callback_context *context = user_data;

    if (context->count < sizeof(context->cards) / sizeof(context->cards[0])) {
        context->cards[context->count++] = *card;
    }
}

int main(void)
{
    const uint8_t first_frame[] = "\x02" "3F00238493" "\r\n\x03";
    const uint8_t two_frames[] = "0000000001\r\nABCDEF1234\r\n";
    const uint8_t raw_frame[] = "\x02" "0123456789" "\r\n\x03";
    const uint8_t event_frames[] =
        "\x02" "0000000002" "\r\n\x03"
        "\x02" "0000000003" "\r\n\x03";
    struct callback_context callback = {0};
    struct pollfd descriptor;
    uint8_t raw_buffer[32];
    size_t raw_length;
    size_t dispatched;
    cr100_handle *reader = NULL;
    cr100_card card;
    char *slave_path;
    int master = -1;
    int result = 0;

    master = posix_openpt(O_RDWR | O_NOCTTY);
    EXPECT(master >= 0);
    EXPECT(grantpt(master) == 0);
    EXPECT(unlockpt(master) == 0);
    slave_path = ptsname(master);
    EXPECT(slave_path != NULL);

    EXPECT(cr100_open(&reader, slave_path, 9600) == CR100_OK);
    EXPECT(strcmp(cr100_device_path(reader), slave_path) == 0);
    descriptor.fd = -1;
    descriptor.events = POLLIN;
    descriptor.revents = 0;
    EXPECT(cr100_get_fd(reader, &descriptor.fd) == CR100_OK);
    EXPECT(descriptor.fd >= 0);

    EXPECT(write(master, first_frame, sizeof(first_frame) - 1) ==
           (ssize_t)(sizeof(first_frame) - 1));
    EXPECT(cr100_read_card(reader, &card, 500) == CR100_OK);
    EXPECT(strcmp(card.hex, "3F00238493") == 0);

    EXPECT(write(master, two_frames, sizeof(two_frames) - 1) ==
           (ssize_t)(sizeof(two_frames) - 1));
    EXPECT(cr100_read_card(reader, &card, 500) == CR100_OK);
    EXPECT(strcmp(card.hex, "0000000001") == 0);
    EXPECT(cr100_read_card(reader, &card, 0) == CR100_OK);
    EXPECT(strcmp(card.hex, "ABCDEF1234") == 0);

    EXPECT(cr100_read_card(reader, &card, 20) == CR100_TIMEOUT);

    EXPECT(write(master, event_frames, sizeof(event_frames) - 1) ==
           (ssize_t)(sizeof(event_frames) - 1));
    EXPECT(poll(&descriptor, 1, 500) == 1);
    EXPECT(descriptor.revents & POLLIN);
    dispatched = 999;
    EXPECT(cr100_dispatch(reader,
                          collect_card,
                          &callback,
                          &dispatched) == CR100_OK);
    EXPECT(dispatched == 2);
    EXPECT(callback.count == 2);
    EXPECT(strcmp(callback.cards[0].hex, "0000000002") == 0);
    EXPECT(strcmp(callback.cards[1].hex, "0000000003") == 0);

    EXPECT(write(master, raw_frame, sizeof(raw_frame) - 1) ==
           (ssize_t)(sizeof(raw_frame) - 1));
    EXPECT(cr100_read_raw(reader,
                          raw_buffer,
                          sizeof(raw_buffer),
                          &raw_length,
                          500) == CR100_OK);
    EXPECT(raw_length == sizeof(raw_frame) - 1);
    EXPECT(memcmp(raw_buffer, raw_frame, raw_length) == 0);
    raw_length = 999;
    EXPECT(cr100_read_raw(reader,
                          raw_buffer,
                          sizeof(raw_buffer),
                          &raw_length,
                          20) == CR100_TIMEOUT);
    EXPECT(raw_length == 0);

cleanup:
    cr100_close(reader);
    if (master >= 0) {
        close(master);
    }

    if (result == 0) {
        puts("All pseudo-terminal reader tests passed.");
    }
    return result;
}

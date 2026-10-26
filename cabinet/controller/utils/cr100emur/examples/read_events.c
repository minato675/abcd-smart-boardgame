#include "cr100emur.h"

#include <poll.h>
#include <stdio.h>

static void print_card(const cr100_card *card, void *user_data)
{
    (void)user_data;
    printf("UID: %s\n", card->hex);
}

int main(void)
{
    cr100_handle *reader = NULL;
    struct pollfd descriptor = {.fd = -1, .events = POLLIN, .revents = 0};
    size_t card_count = 0;
    int result;

    result = cr100_open(&reader, NULL, 0);
    if (result == CR100_OK) {
        result = cr100_get_fd(reader, &descriptor.fd);
    }
    if (result != CR100_OK) {
        fprintf(stderr, "%s\n", cr100_strerror(result));
        cr100_close(reader);
        return 1;
    }

    puts("Waiting for one card through descriptor readiness...");
    result = poll(&descriptor, 1, -1);
    if (result > 0 && (descriptor.revents & POLLIN)) {
        result = cr100_dispatch(
            reader, print_card, NULL, &card_count);
    } else if (result >= 0) {
        result = CR100_ERR_DISCONNECTED;
    } else {
        result = CR100_ERR_IO;
    }

    cr100_close(reader);
    if (result != CR100_OK) {
        fprintf(stderr, "%s\n", cr100_strerror(result));
        return 1;
    }
    return card_count == 0 ? 2 : 0;
}

#include "cr100emur.h"

#include <inttypes.h>
#include <stdio.h>

int main(void)
{
    cr100_handle *reader;
    cr100_card card;
    int result;

    result = cr100_open(&reader, NULL, 0);
    if (result != CR100_OK) {
        fprintf(stderr, "open: %s\n", cr100_strerror(result));
        return 1;
    }

    result = cr100_read_card(reader, &card, -1);
    if (result == CR100_OK) {
        printf("UID %s (%" PRIu64 ")\n", card.hex, card.value);
    } else {
        fprintf(stderr, "read: %s\n", cr100_strerror(result));
    }

    cr100_close(reader);
    return result == CR100_OK ? 0 : 1;
}


#include "cr100emur.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define EXPECT(condition)                                                     \
    do {                                                                      \
        if (!(condition)) {                                                   \
            fprintf(stderr,                                                   \
                    "%s:%d: expectation failed: %s\n",                        \
                    __FILE__,                                                 \
                    __LINE__,                                                 \
                    #condition);                                              \
            return 1;                                                         \
        }                                                                     \
    } while (0)

static int test_vendor_sample(void)
{
    const uint8_t frame[] = "\x02" "3F00238493" "\r\n\x03";
    cr100_parser parser;
    cr100_card cards[2];
    size_t count;

    cr100_parser_init(&parser);
    EXPECT(cr100_parser_feed(&parser,
                             frame,
                             sizeof(frame) - 1,
                             cards,
                             2,
                             &count) == CR100_OK);
    EXPECT(count == 1);
    EXPECT(strcmp(cards[0].hex, "3F00238493") == 0);
    EXPECT(cards[0].value == UINT64_C(0x3F00238493));
    EXPECT(cards[0].uid[0] == 0x3f);
    EXPECT(cards[0].uid[1] == 0x00);
    EXPECT(cards[0].uid[2] == 0x23);
    EXPECT(cards[0].uid[3] == 0x84);
    EXPECT(cards[0].uid[4] == 0x93);
    return 0;
}

static int test_fragmented_and_lowercase(void)
{
    const uint8_t first[] = "\r\n00a1b";
    const uint8_t second[] = "2c3d4\n";
    cr100_parser parser;
    cr100_card card;
    size_t count;

    cr100_parser_init(&parser);
    EXPECT(cr100_parser_feed(&parser,
                             first,
                             sizeof(first) - 1,
                             &card,
                             1,
                             &count) == CR100_OK);
    EXPECT(count == 0);
    EXPECT(cr100_parser_feed(&parser,
                             second,
                             sizeof(second) - 1,
                             &card,
                             1,
                             &count) == CR100_OK);
    EXPECT(count == 1);
    EXPECT(strcmp(card.hex, "00A1B2C3D4") == 0);
    return 0;
}

static int test_back_to_back(void)
{
    const uint8_t frames[] = "0000000001" "ABCDEF1234";
    cr100_parser parser;
    cr100_card cards[2];
    size_t count;

    cr100_parser_init(&parser);
    EXPECT(cr100_parser_feed(&parser,
                             frames,
                             sizeof(frames) - 1,
                             cards,
                             2,
                             &count) == CR100_OK);
    EXPECT(count == 2);
    EXPECT(strcmp(cards[0].hex, "0000000001") == 0);
    EXPECT(strcmp(cards[1].hex, "ABCDEF1234") == 0);
    return 0;
}

static int test_noise_resets_partial_frame(void)
{
    const uint8_t data[] = "1234!DEADBEEF01";
    cr100_parser parser;
    cr100_card card;
    size_t count;

    cr100_parser_init(&parser);
    EXPECT(cr100_parser_feed(&parser,
                             data,
                             sizeof(data) - 1,
                             &card,
                             1,
                             &count) == CR100_OK);
    EXPECT(count == 1);
    EXPECT(strcmp(card.hex, "DEADBEEF01") == 0);
    return 0;
}

static int test_output_overflow(void)
{
    const uint8_t data[] = "0000000001" "0000000002";
    cr100_parser parser;
    cr100_card card;
    size_t count;

    cr100_parser_init(&parser);
    EXPECT(cr100_parser_feed(&parser,
                             data,
                             sizeof(data) - 1,
                             &card,
                             1,
                             &count) == CR100_ERR_OVERFLOW);
    EXPECT(count == 1);
    EXPECT(strcmp(card.hex, "0000000001") == 0);
    return 0;
}

int main(void)
{
    int failures = 0;

    failures += test_vendor_sample();
    failures += test_fragmented_and_lowercase();
    failures += test_back_to_back();
    failures += test_noise_resets_partial_frame();
    failures += test_output_overflow();

    if (failures != 0) {
        fprintf(stderr, "%d parser test(s) failed\n", failures);
        return 1;
    }
    puts("All parser tests passed.");
    return 0;
}

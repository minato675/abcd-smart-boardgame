#ifndef CR100EMUR_H
#define CR100EMUR_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define CR100EMUR_VERSION_MAJOR 0
#define CR100EMUR_VERSION_MINOR 2
#define CR100EMUR_VERSION_PATCH 0

#define CR100EMUR_USB_VENDOR_ID 0x10c4
#define CR100EMUR_USB_PRODUCT_ID 0xea60
#define CR100EMUR_DEFAULT_BAUD 9600
#define CR100EMUR_UID_BYTES 5
#define CR100EMUR_UID_HEX_LENGTH 10

enum cr100_status {
    CR100_OK = 0,
    CR100_TIMEOUT = 1,
    CR100_ERR_ARGUMENT = -1,
    CR100_ERR_NOT_FOUND = -2,
    CR100_ERR_ACCESS = -3,
    CR100_ERR_IO = -4,
    CR100_ERR_BAUD = -5,
    CR100_ERR_DISCONNECTED = -6,
    CR100_ERR_OVERFLOW = -7
};

typedef struct cr100_handle cr100_handle;

typedef struct cr100_card {
    uint8_t uid[CR100EMUR_UID_BYTES];
    char hex[CR100EMUR_UID_HEX_LENGTH + 1];
    uint64_t value;
} cr100_card;

/*
 * Called synchronously by cr100_dispatch() for each complete card.
 *
 * The card pointer is valid only for the duration of the callback. Copy the
 * value if it must outlive the callback. Do not close or read from handle
 * inside the callback.
 */
typedef void (*cr100_card_callback)(const cr100_card *card, void *user_data);

/*
 * Incremental parser state. Applications normally use cr100_read_card()
 * instead. The parser API is public so captured streams and non-POSIX
 * transports can use the same protocol implementation.
 */
typedef struct cr100_parser {
    char candidate[CR100EMUR_UID_HEX_LENGTH + 1];
    size_t candidate_length;
} cr100_parser;

/*
 * Locate the stable device node for a CR-100EMUR.
 *
 * The search checks /dev/cr100emur first, then the CP2102 by-id node created
 * by udev. The resulting path is copied into path.
 */
int cr100_find_device(char *path, size_t path_size);

/*
 * Open and configure the reader as raw 8-N-1 serial.
 *
 * Pass NULL or an empty device string to auto-discover the reader. baud is a
 * numeric rate such as 9600; pass 0 to use CR100EMUR_DEFAULT_BAUD.
 */
int cr100_open(cr100_handle **handle, const char *device, unsigned int baud);

void cr100_close(cr100_handle *handle);

const char *cr100_device_path(const cr100_handle *handle);

/*
 * Return the non-blocking serial descriptor for integration with poll(2),
 * epoll(7), QSocketNotifier, asyncio, or another readiness-based event loop.
 *
 * The descriptor remains owned by handle and must not be closed by the
 * application. Returns CR100_OK and initializes *fd on success.
 */
int cr100_get_fd(const cr100_handle *handle, int *fd);

/*
 * Wait for one card.
 *
 * timeout_ms < 0 waits indefinitely, 0 only consumes already available data,
 * and a positive value bounds the wait. Returns CR100_OK, CR100_TIMEOUT, or a
 * negative enum cr100_status value.
 */
int cr100_read_card(cr100_handle *handle, cr100_card *card, int timeout_ms);

/*
 * Drain every complete card currently available without blocking.
 *
 * Call this after the descriptor returned by cr100_get_fd() becomes readable.
 * callback is invoked synchronously once per card. Partial serial frames stay
 * in the parser until a later readiness notification. *card_count is always
 * initialized, including on error.
 */
int cr100_dispatch(cr100_handle *handle,
                   cr100_card_callback callback,
                   void *user_data,
                   size_t *card_count);

/*
 * Read the unparsed serial stream for protocol diagnostics.
 *
 * *data_length is always initialized. Do not interleave this call with
 * cr100_read_card() on the same handle: raw reads intentionally bypass the
 * parser and its pending-card queue.
 */
int cr100_read_raw(cr100_handle *handle,
                   uint8_t *data,
                   size_t data_capacity,
                   size_t *data_length,
                   int timeout_ms);

void cr100_parser_init(cr100_parser *parser);

/*
 * Feed arbitrary stream fragments into the parser.
 *
 * Complete cards are placed in cards and *card_count is always initialized.
 * A frame is the vendor-observed 10 ASCII hexadecimal UID characters.
 * Control characters, whitespace, and other non-hex bytes delimit frames.
 */
int cr100_parser_feed(cr100_parser *parser,
                      const uint8_t *data,
                      size_t data_length,
                      cr100_card *cards,
                      size_t card_capacity,
                      size_t *card_count);

int cr100_card_from_hex(const char *hex, cr100_card *card);

const char *cr100_strerror(int status);

#ifdef __cplusplus
}
#endif

#endif

#include "cr100emur.h"

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define CR100_PATH_CAPACITY 512
#define CR100_PENDING_CAPACITY 16
#define CR100_READ_BUFFER_SIZE 128

struct cr100_handle {
    int fd;
    char path[CR100_PATH_CAPACITY];
    cr100_parser parser;
    cr100_card pending[CR100_PENDING_CAPACITY];
    size_t pending_head;
    size_t pending_count;
};

static int copy_path(char *destination,
                     size_t destination_size,
                     const char *source)
{
    size_t length;

    if (destination == NULL || source == NULL || destination_size == 0) {
        return CR100_ERR_ARGUMENT;
    }

    length = strlen(source);
    if (length + 1 > destination_size) {
        return CR100_ERR_OVERFLOW;
    }

    memcpy(destination, source, length + 1);
    return CR100_OK;
}

int cr100_find_device(char *path, size_t path_size)
{
    static const char *const exact_candidates[] = {
        "/dev/cr100emur",
        "/dev/serial/by-id/"
        "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
    };
    glob_t matches;
    size_t index;
    int result;

    if (path == NULL || path_size == 0) {
        return CR100_ERR_ARGUMENT;
    }

    for (index = 0;
         index < sizeof(exact_candidates) / sizeof(exact_candidates[0]);
         ++index) {
        if (access(exact_candidates[index], F_OK) == 0) {
            return copy_path(path, path_size, exact_candidates[index]);
        }
    }

    memset(&matches, 0, sizeof(matches));
    result = glob("/dev/serial/by-id/*CP210*0001*", 0, NULL, &matches);
    if (result == 0 && matches.gl_pathc > 0) {
        result = copy_path(path, path_size, matches.gl_pathv[0]);
        globfree(&matches);
        return result;
    }
    globfree(&matches);

    path[0] = '\0';
    return CR100_ERR_NOT_FOUND;
}

static int baud_to_termios(unsigned int baud, speed_t *speed)
{
    if (speed == NULL) {
        return CR100_ERR_ARGUMENT;
    }

    switch (baud) {
    case 1200:
        *speed = B1200;
        break;
    case 2400:
        *speed = B2400;
        break;
    case 4800:
        *speed = B4800;
        break;
    case 9600:
        *speed = B9600;
        break;
    case 19200:
        *speed = B19200;
        break;
    case 38400:
        *speed = B38400;
        break;
    case 57600:
        *speed = B57600;
        break;
    case 115200:
        *speed = B115200;
        break;
    default:
        return CR100_ERR_BAUD;
    }

    return CR100_OK;
}

static int configure_serial(int fd, unsigned int baud)
{
    struct termios options;
    speed_t speed;
    int result;

    result = baud_to_termios(baud, &speed);
    if (result != CR100_OK) {
        return result;
    }

    if (tcgetattr(fd, &options) != 0) {
        return CR100_ERR_IO;
    }

    cfmakeraw(&options);
    options.c_cflag &= ~(CSIZE | PARENB | CSTOPB | CRTSCTS);
    options.c_cflag |= CS8 | CLOCAL | CREAD;
    options.c_iflag &= ~(IXON | IXOFF | IXANY);
    options.c_cc[VMIN] = 0;
    options.c_cc[VTIME] = 0;

    if (cfsetispeed(&options, speed) != 0 ||
        cfsetospeed(&options, speed) != 0 ||
        tcsetattr(fd, TCSANOW, &options) != 0) {
        return CR100_ERR_IO;
    }

    return CR100_OK;
}

int cr100_open(cr100_handle **handle,
               const char *device,
               unsigned int baud)
{
    cr100_handle *reader;
    char discovered[CR100_PATH_CAPACITY];
    const char *selected_device;
    int saved_errno;
    int result;

    if (handle == NULL) {
        return CR100_ERR_ARGUMENT;
    }
    *handle = NULL;

    selected_device = device;
    if (selected_device == NULL || selected_device[0] == '\0') {
        result = cr100_find_device(discovered, sizeof(discovered));
        if (result != CR100_OK) {
            return result;
        }
        selected_device = discovered;
    }

    if (baud == 0) {
        baud = CR100EMUR_DEFAULT_BAUD;
    }

    reader = calloc(1, sizeof(*reader));
    if (reader == NULL) {
        return CR100_ERR_IO;
    }
    reader->fd = -1;

    result = copy_path(reader->path, sizeof(reader->path), selected_device);
    if (result != CR100_OK) {
        free(reader);
        return result;
    }

    reader->fd = open(selected_device, O_RDONLY | O_NOCTTY | O_NONBLOCK);
    if (reader->fd < 0) {
        saved_errno = errno;
        free(reader);
        errno = saved_errno;
        if (saved_errno == EACCES || saved_errno == EPERM) {
            return CR100_ERR_ACCESS;
        }
        if (saved_errno == ENOENT || saved_errno == ENODEV) {
            return CR100_ERR_NOT_FOUND;
        }
        return CR100_ERR_IO;
    }

    result = configure_serial(reader->fd, baud);
    if (result != CR100_OK) {
        saved_errno = errno;
        close(reader->fd);
        free(reader);
        errno = saved_errno;
        return result;
    }

    cr100_parser_init(&reader->parser);
    *handle = reader;
    return CR100_OK;
}

void cr100_close(cr100_handle *handle)
{
    if (handle == NULL) {
        return;
    }
    if (handle->fd >= 0) {
        close(handle->fd);
    }
    free(handle);
}

const char *cr100_device_path(const cr100_handle *handle)
{
    return handle == NULL ? NULL : handle->path;
}

int cr100_get_fd(const cr100_handle *handle, int *fd)
{
    if (fd != NULL) {
        *fd = -1;
    }
    if (handle == NULL || fd == NULL || handle->fd < 0) {
        return CR100_ERR_ARGUMENT;
    }

    *fd = handle->fd;
    return CR100_OK;
}

void cr100_parser_init(cr100_parser *parser)
{
    if (parser == NULL) {
        return;
    }
    memset(parser, 0, sizeof(*parser));
}

static int hex_nibble(char character)
{
    if (character >= '0' && character <= '9') {
        return character - '0';
    }
    if (character >= 'A' && character <= 'F') {
        return character - 'A' + 10;
    }
    if (character >= 'a' && character <= 'f') {
        return character - 'a' + 10;
    }
    return -1;
}

int cr100_card_from_hex(const char *hex, cr100_card *card)
{
    size_t index;
    uint64_t value;

    if (hex == NULL || card == NULL ||
        strlen(hex) != CR100EMUR_UID_HEX_LENGTH) {
        return CR100_ERR_ARGUMENT;
    }

    memset(card, 0, sizeof(*card));
    value = 0;
    for (index = 0; index < CR100EMUR_UID_HEX_LENGTH; ++index) {
        int nibble = hex_nibble(hex[index]);

        if (nibble < 0) {
            return CR100_ERR_ARGUMENT;
        }
        card->hex[index] = (char)toupper((unsigned char)hex[index]);
        value = (value << 4) | (unsigned int)nibble;
    }
    card->hex[CR100EMUR_UID_HEX_LENGTH] = '\0';
    card->value = value;

    for (index = 0; index < CR100EMUR_UID_BYTES; ++index) {
        int high = hex_nibble(card->hex[index * 2]);
        int low = hex_nibble(card->hex[index * 2 + 1]);
        card->uid[index] = (uint8_t)((high << 4) | low);
    }

    return CR100_OK;
}

int cr100_parser_feed(cr100_parser *parser,
                      const uint8_t *data,
                      size_t data_length,
                      cr100_card *cards,
                      size_t card_capacity,
                      size_t *card_count)
{
    size_t produced;
    size_t index;
    int overflow;

    if (card_count != NULL) {
        *card_count = 0;
    }
    if (parser == NULL || card_count == NULL ||
        (data == NULL && data_length != 0) ||
        (cards == NULL && card_capacity != 0)) {
        return CR100_ERR_ARGUMENT;
    }

    produced = 0;
    overflow = 0;
    for (index = 0; index < data_length; ++index) {
        unsigned char byte = data[index];

        if (isxdigit(byte)) {
            parser->candidate[parser->candidate_length++] =
                (char)toupper(byte);

            if (parser->candidate_length == CR100EMUR_UID_HEX_LENGTH) {
                parser->candidate[CR100EMUR_UID_HEX_LENGTH] = '\0';
                if (produced < card_capacity) {
                    cr100_card_from_hex(parser->candidate, &cards[produced]);
                    ++produced;
                } else {
                    overflow = 1;
                }
                parser->candidate_length = 0;
                parser->candidate[0] = '\0';
            }
        } else {
            parser->candidate_length = 0;
            parser->candidate[0] = '\0';
        }
    }

    *card_count = produced;
    return overflow ? CR100_ERR_OVERFLOW : CR100_OK;
}

static int pending_pop(cr100_handle *handle, cr100_card *card)
{
    if (handle->pending_count == 0) {
        return 0;
    }

    *card = handle->pending[handle->pending_head];
    handle->pending_head =
        (handle->pending_head + 1) % CR100_PENDING_CAPACITY;
    --handle->pending_count;
    return 1;
}

static void pending_push(cr100_handle *handle, const cr100_card *card)
{
    size_t tail;

    if (handle->pending_count == CR100_PENDING_CAPACITY) {
        return;
    }
    tail = (handle->pending_head + handle->pending_count) %
           CR100_PENDING_CAPACITY;
    handle->pending[tail] = *card;
    ++handle->pending_count;
}

static int64_t monotonic_milliseconds(void)
{
    struct timespec now;

    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        return -1;
    }
    return (int64_t)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int cr100_read_card(cr100_handle *handle, cr100_card *card, int timeout_ms)
{
    uint8_t buffer[CR100_READ_BUFFER_SIZE];
    cr100_card parsed[CR100_PENDING_CAPACITY];
    int64_t deadline;

    if (handle == NULL || card == NULL || timeout_ms < -1) {
        return CR100_ERR_ARGUMENT;
    }
    if (pending_pop(handle, card)) {
        return CR100_OK;
    }

    deadline = -1;
    if (timeout_ms >= 0) {
        int64_t now = monotonic_milliseconds();
        if (now < 0) {
            return CR100_ERR_IO;
        }
        deadline = now + timeout_ms;
    }

    for (;;) {
        struct pollfd descriptor;
        int poll_timeout;
        int poll_result;
        ssize_t bytes_read;
        size_t parsed_count;
        size_t index;
        int parse_result;

        poll_timeout = -1;
        if (deadline >= 0) {
            int64_t remaining = deadline - monotonic_milliseconds();
            if (remaining <= 0 && timeout_ms != 0) {
                return CR100_TIMEOUT;
            }
            poll_timeout = remaining > 0 ? (int)remaining : 0;
        }

        descriptor.fd = handle->fd;
        descriptor.events = POLLIN;
        descriptor.revents = 0;
        poll_result = poll(&descriptor, 1, poll_timeout);
        if (poll_result == 0) {
            return CR100_TIMEOUT;
        }
        if (poll_result < 0) {
            if (errno == EINTR) {
                continue;
            }
            return CR100_ERR_IO;
        }
        if (descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) {
            return CR100_ERR_DISCONNECTED;
        }
        if (!(descriptor.revents & POLLIN)) {
            continue;
        }

        bytes_read = read(handle->fd, buffer, sizeof(buffer));
        if (bytes_read < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
                continue;
            }
            if (errno == ENODEV || errno == EIO) {
                return CR100_ERR_DISCONNECTED;
            }
            return CR100_ERR_IO;
        }
        if (bytes_read == 0) {
            continue;
        }

        parse_result = cr100_parser_feed(&handle->parser,
                                         buffer,
                                         (size_t)bytes_read,
                                         parsed,
                                         CR100_PENDING_CAPACITY,
                                         &parsed_count);
        if (parse_result != CR100_OK) {
            return parse_result;
        }
        if (parsed_count == 0) {
            continue;
        }

        *card = parsed[0];
        for (index = 1; index < parsed_count; ++index) {
            pending_push(handle, &parsed[index]);
        }
        return CR100_OK;
    }
}

int cr100_dispatch(cr100_handle *handle,
                   cr100_card_callback callback,
                   void *user_data,
                   size_t *card_count)
{
    cr100_card card;
    size_t dispatched;

    if (card_count != NULL) {
        *card_count = 0;
    }
    if (handle == NULL || callback == NULL || card_count == NULL) {
        return CR100_ERR_ARGUMENT;
    }

    dispatched = 0;
    for (;;) {
        int result = cr100_read_card(handle, &card, 0);

        if (result == CR100_TIMEOUT) {
            *card_count = dispatched;
            return CR100_OK;
        }
        if (result != CR100_OK) {
            *card_count = dispatched;
            return result;
        }

        callback(&card, user_data);
        ++dispatched;
    }
}

int cr100_read_raw(cr100_handle *handle,
                   uint8_t *data,
                   size_t data_capacity,
                   size_t *data_length,
                   int timeout_ms)
{
    int64_t deadline;

    if (data_length != NULL) {
        *data_length = 0;
    }
    if (handle == NULL || data == NULL || data_capacity == 0 ||
        data_length == NULL || timeout_ms < -1) {
        return CR100_ERR_ARGUMENT;
    }

    deadline = -1;
    if (timeout_ms >= 0) {
        int64_t now = monotonic_milliseconds();
        if (now < 0) {
            return CR100_ERR_IO;
        }
        deadline = now + timeout_ms;
    }

    for (;;) {
        struct pollfd descriptor;
        int poll_timeout;
        int poll_result;
        ssize_t bytes_read;

        poll_timeout = -1;
        if (deadline >= 0) {
            int64_t now = monotonic_milliseconds();
            int64_t remaining;

            if (now < 0) {
                return CR100_ERR_IO;
            }
            remaining = deadline - now;
            if (remaining <= 0 && timeout_ms != 0) {
                return CR100_TIMEOUT;
            }
            poll_timeout = remaining > 0 ? (int)remaining : 0;
        }

        descriptor.fd = handle->fd;
        descriptor.events = POLLIN;
        descriptor.revents = 0;
        poll_result = poll(&descriptor, 1, poll_timeout);
        if (poll_result == 0) {
            return CR100_TIMEOUT;
        }
        if (poll_result < 0) {
            if (errno == EINTR) {
                continue;
            }
            return CR100_ERR_IO;
        }
        if (descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) {
            return CR100_ERR_DISCONNECTED;
        }
        if (!(descriptor.revents & POLLIN)) {
            continue;
        }

        bytes_read = read(handle->fd, data, data_capacity);
        if (bytes_read < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
                continue;
            }
            if (errno == ENODEV || errno == EIO) {
                return CR100_ERR_DISCONNECTED;
            }
            return CR100_ERR_IO;
        }
        if (bytes_read == 0) {
            continue;
        }

        *data_length = (size_t)bytes_read;
        return CR100_OK;
    }
}

const char *cr100_strerror(int status)
{
    switch (status) {
    case CR100_OK:
        return "success";
    case CR100_TIMEOUT:
        return "timed out waiting for a card";
    case CR100_ERR_ARGUMENT:
        return "invalid argument";
    case CR100_ERR_NOT_FOUND:
        return "CR-100EMUR device not found";
    case CR100_ERR_ACCESS:
        return "permission denied opening the CR-100EMUR";
    case CR100_ERR_IO:
        return "serial I/O error";
    case CR100_ERR_BAUD:
        return "unsupported baud rate";
    case CR100_ERR_DISCONNECTED:
        return "CR-100EMUR disconnected";
    case CR100_ERR_OVERFLOW:
        return "output buffer is too small";
    default:
        return "unknown CR-100EMUR error";
    }
}

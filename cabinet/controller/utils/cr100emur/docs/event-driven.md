# Event-driven card reading

## What “interrupt based” means on Linux

The CR-100EMUR is a CP2102 USB-to-UART device. The kernel's `cp210x` driver
handles the hardware and USB interrupts. A userspace controller receives the
corresponding event as readability on the serial file descriptor.

The SDK therefore blocks in the kernel through `poll(2)`, `epoll(7)`, or
asyncio's selector. It does not repeatedly check the reader on a timer.

## C and an existing controller loop

`cr100_get_fd()` returns a borrowed non-blocking descriptor. Keep the
`cr100_handle` open, register the descriptor for readable events, and call
`cr100_dispatch()` when notified:

```c
static void on_card(const cr100_card *card, void *context)
{
    controller_enqueue(context, card->hex);
}

int fd;
cr100_handle *reader;
cr100_open(&reader, NULL, 0);
cr100_get_fd(reader, &fd);

/* Register fd with the controller's epoll instance here. */

size_t count;
cr100_dispatch(reader, on_card, controller, &count);
```

`cr100_dispatch()` is non-blocking. It invokes the callback synchronously for
every complete card already buffered and retains a partial serial frame for
the next readability notification. Do not close or read the same handle from
inside the callback.

## C++ callbacks

`EventReader` owns a `Reader` and a background thread that sleeps in
`poll(2)`. `stop()` wakes that thread through an internal pipe and joins it,
so shutdown does not wait for a card.

```cpp
cr100emur::EventReader reader{
    [](const cr100emur::Card &card) {
        controller_queue.push(card);
    },
    [](std::exception_ptr failure) {
        log_reader_failure(failure);
    }};

reader.start();
// Run the controller.
reader.stop();
```

Card and error handlers run on the worker thread. They should enqueue work
for the controller rather than performing long operations. A handler can call
`request_stop()`, while an owning/control thread should call `stop()` to join.
`last_error()` retains the worker failure for later inspection.

If the application already has an event loop, avoid the extra thread:
register `Reader::file_descriptor()` and invoke `Reader::dispatch(handler)`
after a readable event.

## Python asyncio

`AsyncReader` registers `Reader.fileno()` with the running asyncio selector.
Cards can be consumed with `await read()`, an async iterator, a callback, or
both:

```python
async with AsyncReader(on_card=controller.on_card) as reader:
    async for card in reader:
        await audit_log.write(card.hex)
```

Synchronous callbacks execute on the asyncio thread and must return quickly.
An `async def` callback is scheduled as a task. Callback exceptions are
reported through the loop's exception handler; serial/device failures are
raised by `read()`.

Always close the reader, preferably with `async with`, so its file descriptor
is removed from the event loop before the native handle is closed.

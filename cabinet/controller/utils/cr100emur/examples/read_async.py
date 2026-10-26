import asyncio

from cr100emur import AsyncReader, Card


async def main() -> None:
    received = asyncio.Event()

    def on_card(card: Card) -> None:
        print(card.hex, card.uid.hex(), card.value)
        received.set()

    async with AsyncReader(on_card=on_card):
        await received.wait()


asyncio.run(main())

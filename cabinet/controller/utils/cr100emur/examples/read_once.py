from cr100emur import Reader


with Reader() as reader:
    card = reader.read()
    assert card is not None
    print(f"UID {card.hex} ({card.value})")


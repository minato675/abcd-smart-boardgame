#include "cr100emur.hpp"

#include <iostream>

int main()
{
    try {
        cr100emur::Reader reader;
        const cr100emur::Card card = reader.read();

        std::cout << "UID " << card.hex << " (" << card.value << ")\n";
        return 0;
    } catch (const cr100emur::Error &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}


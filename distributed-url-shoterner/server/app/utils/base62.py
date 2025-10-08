ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def encode(num):
    """Convert a positive integer to a base62 string."""
    if num == 0:
        return ALPHABET[0]
    arr = []
    base = len(ALPHABET)
    while num:
        rem = num % base
        num = num // base
        arr.append(ALPHABET[rem])
    arr.reverse()
    return ''.join(arr)


def decode(string):
    """Convert a base62 string to a positive integer."""
    base = len(ALPHABET)
    strlen = len(string)
    num = 0

    idx = 0
    for char in string:
        power = (strlen - (idx + 1))
        num += ALPHABET.index(char) * (base ** power)
        idx += 1

    return num
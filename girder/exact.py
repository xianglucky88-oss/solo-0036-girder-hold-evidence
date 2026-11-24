from fractions import Fraction


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Fraction(ordered[middle])
    return Fraction(ordered[middle - 1] + ordered[middle], 2)


def encode(value):
    if value is None:
        return None
    return int(value) if value.denominator == 1 else str(value)

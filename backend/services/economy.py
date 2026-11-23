"""Shared gold pricing and fee rules."""

GOLD_COMMISSION_PERCENT = 1
MAX_GOLD = 2_147_483_647


def supply_price(base, stock, capacity, minimum_percent, maximum_percent):
    capacity = max(1, capacity)
    stock = max(0, min(stock, capacity))
    numerator = base * (maximum_percent * (capacity - stock) + minimum_percent * stock)
    denominator = 100 * capacity
    minimum = (base * minimum_percent + 99) // 100
    maximum = base * maximum_percent // 100
    return min(maximum, max(minimum, (numerator + denominator // 2) // denominator))


def gold_commission(amount, *, direct_transfer=False):
    return 0 if direct_transfer else (amount * GOLD_COMMISSION_PERCENT + 99) // 100

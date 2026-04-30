from common.database import OrderStatus

hehe = OrderStatus.Cancelled


def get_enum_values(enum_class):
    return enum_class.value

print(get_enum_values(hehe))
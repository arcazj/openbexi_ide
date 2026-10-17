"""Click beside a line number to add a breakpoint, then choose Debug."""
import asyncio


def total(values):
    result = sum(values)
    return result


async def main():
    values = [3, 5, 8]
    answer = total(values)
    await asyncio.sleep(0.05)
    print(f"Values: {values}; total: {answer}")


asyncio.run(main())

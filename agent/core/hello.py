"""Core hello util""" 
from typing import Final

GREETING: Final[str] = "Hello"

def say_hello(name: str) -> str:
    return f"{GREETING}, {name}!"

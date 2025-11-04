import unittest

from agent.core.hello import say_hello


class HelloTests(unittest.TestCase):
    def test_say_hello(self) -> None:
        self.assertEqual(say_hello("World"), "Hello, World!")


if __name__ == "__main__":
    unittest.main()

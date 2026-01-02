import unittest

from main import Lexer



class TestLexer(unittest.TestCase):

    def test_empty(self):
        lexer = Lexer("")
        tokens = lexer.tokenize()
        self.assertEqual(len(tokens), 1)  # will expect an EOF token

import unittest

from main import Lexer , TokenType


class TestLexer(unittest.TestCase):

    def test_empty(self):
        lexer = Lexer("")
        tokens = lexer.tokenize()
        self.assertEqual(len(tokens), 1)  # will expect an EOF token
        self.assertEqual(tokens[0].type, TokenType.EOF)

    def test_numbers(self):
        lexer = Lexer("123 45.67")
        tokens = lexer.tokenize()
        self.assertEqual(tokens[0].type, TokenType.NUMBER)
        self.assertEqual(tokens[0].value, 123)
        self.assertEqual(tokens[1].type, TokenType.NUMBER)
        self.assertEqual(tokens[1].value, 45.67)

    def test_strings(self):
        lexer = Lexer('"hello" "world"')
        tokens = lexer.tokenize()
        self.assertEqual(tokens[0].type, TokenType.STRING)
        self.assertEqual(tokens[0].value, "hello")
        self.assertEqual(tokens[1].type, TokenType.STRING)
        self.assertEqual(tokens[1].value, "world")

    def test_operators(self):
        lexer = Lexer("+ - * / = == != < > <= >=")
        tokens = lexer.tokenize()
        expected_types = [
            TokenType.PLUS,
            TokenType.MINUS,
            TokenType.MULTIPLY,
            TokenType.DIVIDE,
            TokenType.ASSIGN,
            TokenType.EQUALS,
            TokenType.NOT_EQUALS,
            TokenType.LESS,
            TokenType.GREATER,
            TokenType.LESS_EQUAL,
            TokenType.GREATER_EQUAL,
            TokenType.EOF,
        ]
        self.assertEqual(len(tokens), len(expected_types))
        for i, token in enumerate(tokens):
            self.assertEqual(token.type, expected_types[i])

    def test_keywords(self):
        lexer = Lexer("let if else while fn return print true false")
        tokens = lexer.tokenize()
        expected_types = [
            TokenType.LET,
            TokenType.IF,
            TokenType.ELSE,
            TokenType.WHILE,
            TokenType.FUNC,
            TokenType.RETURN,
            TokenType.PRINT,
            TokenType.TRUE,
            TokenType.FALSE,
            TokenType.EOF,
        ]
        self.assertEqual(len(tokens), len(expected_types))
        for i, token in enumerate(tokens):
            self.assertEqual(token.type, expected_types[i])

    def test_identifiers(self):
        lexer = Lexer("abc _var x1")
        tokens = lexer.tokenize()
        self.assertEqual(tokens[0].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[0].value, "abc")
        self.assertEqual(tokens[1].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[1].value, "_var")
        self.assertEqual(tokens[2].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[2].value, "x1")

    def test_skip_whitespace_and_comments(self):
        lexer = Lexer(
            """
        // This is a comment
        let x = 10; // Another comment
        """
        )
        tokens = lexer.tokenize()
        self.assertEqual(tokens[0].type, TokenType.LET)
        self.assertEqual(tokens[1].type, TokenType.IDENTIFIER)
        self.assertEqual(tokens[2].type, TokenType.ASSIGN)
        self.assertEqual(tokens[3].type, TokenType.NUMBER)
        self.assertEqual(tokens[4].type, TokenType.SEMICOLON)
        self.assertEqual(tokens[5].type, TokenType.EOF)


if __name__ == "__main__":
    unittest.main()

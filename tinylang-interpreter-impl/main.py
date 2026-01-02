from typing import Enum


class TokenType(Enum):
    """All token types for the language"""

    NUMBER = auto()
    STRING = auto()


@dataclass
class Token:
    """Rep a single token"""

    type: TokenType
    value: Any
    line: int
    column: int


class Lexer:
    def __init(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens = []

    def advance(self):
        """move to next char"""
        if self.current_char:
            if current_char == "\n":
                self.line += 1
                self.column = 1
            else:
                self.column += 1
            self.pos += 1

    def skip_whitespace(self):
        """
        Skip whitespaces and comments
        """
        while self.current_char() and self.current_char in " \t\n\r":
            self.advance()

        # skipp comments
        if self.current_char() == "/" and self.peek_char() == "/":
            while self.current_char() and self.current_char() != "\n":
                self.advance()
            self.skip_whitespace()

    def current_char(self):
        """get current character"""
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]

    def peek_char(self):
        """look at nxt char without moving forward"""
        if self.pos + 1 >= len(self.source):
            return None
        return self.source[self.pos + 1]

    def tokenize(self):
        """
        Covert source code to tokens list
        """

        while self.pos < len(self.source):
            self.skip_whitespace()

            if self.current_char() is None:
                break

            char = self.current_char()
            col = self.column

            if char.isdigit():
                self.tokens.append(self.read_number())

            elif char == '"':  # open quote
                self.tokens.append(self.read_string())

    def read_string(self) -> Token:
        """
        Read a string token
        """
        start_col = self.column
        self.advance()  # skip opening quote

        string_value = ""

        while self.current_char() and self.current_char() != '"':
            if self.current_char() == "\\" and self.peek_char() == '"':
                # escape char or closing quote
                self.advance()
                string_value += '"'
                self.advance()
            else:
                string_value += self.current_char()
                self.advance()

        self.advance()  # skip closing quote
        return Token(TokenType.STRING, string_value, self.line, start_col)

    def read_number(self) -> Token:
        """
        Read a number token
        """
        start_col = self.column
        num_str = ""

        decimal_found = False

        while self.current_char() and (
            self.current_char().isdigit() or self.current_char() == "."
        ):
            if self.current_char() == ".":
                decimal_found = True
            num_str += self.current_char()
            self.advance()

        value = float(num_str) if decimal_found else int(num_str)
        return Token(TokenType.NUMBER, value, self.line, start_col)


class Parser:
    def __init__(self, tokens: list):
        pass

    def parse(self):
        pass


class Interpreter:
    def __init__(self, ast):
        pass

    def interpret(self):
        pass


# I will be creating a simple programming language interpreter


# I will be copying the javascript syntax

# Steps
#  Lexa

#  Parse

#  Execute


if __name__ == "__main__":
    print("Simple programming language interpreter")

class Lexer:
    def __init(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1

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

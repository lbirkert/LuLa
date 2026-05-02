# LuLaC

This is the compiler for the LuLa language. It compiles source code (.lula)
to an immediate representation - for now this only includes LLVM IR. The program
can then be further compiled down to an executable using the LLVM compiler.

## How this works

The compiler works in different stages.

### 1. Lexing (lexer.py)

Here the compiler converts the raw source code character sequence into longer connected
tokens which have semantic meaning. Such tokens include for example a String token, a Number
token or different Keyword tokens. The difficulty exists mostly in parsing difficult token
structures like numbers which can - apart from being hexadecimal or binary - also have a type suffix:

*examples of valid number token's values*
```
"10"
=> NumberLiteral(type=None, value=10)

"0b101010u8"
=> NumberLiteral(type=<IntType.U8: ('u8', False, 8)>, value=42)

"0xABCDEFi32"
=> NumberLiteral(type=<IntType.I32: ('i32', True, 32)>, value=11259375)

"1.0e-5f32"
=> NumberLiteral(type=<FloatType.F32: ('f32', 32)>, value=1e-05)
```

----

### 2. Parser (parser.py)

Here the compiler uses this sequence of tokens to generate an AST-representation (abstract syntax
tree) of the programm. It parses certain operations in a tree-wise manner. An example of this is
the binary expression which has a LHS (left hand side) and a RHS (right hand side). Both LHS and RHS
are of type expression and can therefore point to other operations. Below you can see an example
of how this will look like.

*expression (1 + 2) + 3*
```
        BinaryExpr(+)
           /      \
  BinaryExpr(+)   NumberExpr(3)
      /     \
NumberExpr(1) NumberExpr(2)
```

----

### Example

I chose to include a medium complex example of how exactly this compiling process looks
for demonstration of the complexity and amount of nesting such an AST has.

*input source code*
```lula
fun greet(name: str): string
    ret "Hello " + name

fun add(a: i32, b: i32): i32
    ret a + b

fun main()
    var greeting = greet("Lucas")
    print(greeting)

    print(add(0xabc, 0b101))

main()
```

*generated tokens (lexer.py)*
```
TokenType.KEYWORD_FUN: fun
TokenType.IDENTIFIER: greet
TokenType.LPAREN: None
TokenType.IDENTIFIER: name
TokenType.COLON: None
TokenType.IDENTIFIER: str
TokenType.RPAREN: None
TokenType.COLON: None
TokenType.IDENTIFIER: string
TokenType.NEWLINE: None
TokenType.INDENT: 1
TokenType.KEYWORD_RET: ret
TokenType.STRING: Hello 
TokenType.PLUS: None
TokenType.IDENTIFIER: name
TokenType.NEWLINE: None
TokenType.DEDENT: 0
...
TokenType.IDENTIFIER: print
TokenType.LPAREN: None
TokenType.IDENTIFIER: add
TokenType.LPAREN: None
TokenType.NUMBER: NumberLiteral(type=None, value=2748)
TokenType.COMMA: None
TokenType.NUMBER: NumberLiteral(type=None, value=5)
TokenType.RPAREN: None
TokenType.RPAREN: None
TokenType.NEWLINE: None
TokenType.DEDENT: 0
TokenType.IDENTIFIER: main
TokenType.LPAREN: None
TokenType.RPAREN: None
TokenType.NEWLINE: None
TokenType.EOF: None
```

*generated AST (parser.py)*
```
Program
  Functions:
    Function(greet)
      Args:
        Arg(name) : TypeRef(str)
      ReturnType:
        TypeRef(string)
      Body:
        ReturnStmt
          BinaryExpr(ADD)
            StringExpr("Hello ")
            IdentifierExpr(name)
    Function(add)
      Args:
        Arg(a) : TypeRef(i32)
        Arg(b) : TypeRef(i32)
      ReturnType:
        TypeRef(i32)
      Body:
        ReturnStmt
          BinaryExpr(ADD)
            IdentifierExpr(a)
            IdentifierExpr(b)
    Function(main)
      Args:
        <no args>
      ReturnType:
        <no return type>
      Body:
        VarDeclStmt(greeting)
          Type:
          <no type>
          Value:
          CallExpr
            IdentifierExpr(greet)
            Arg(None)
              StringExpr("Lucas")
        ExprStmt
          CallExpr
            IdentifierExpr(print)
            Arg(None)
              IdentifierExpr(greeting)
        ExprStmt
          CallExpr
            IdentifierExpr(print)
            Arg(None)
              CallExpr
                IdentifierExpr(add)
                Arg(None)
                  NumberExpr(2748)
                Arg(None)
                  NumberExpr(5)
  Statements:
    ExprStmt
      CallExpr
        IdentifierExpr(main)
        <no args>
```

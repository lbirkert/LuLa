from .core import SourceSpan, Ident

from dataclasses import dataclass
from enum import Enum
from typing import Any
from pathlib import Path
from enum import Enum

@dataclass
class NumberLiteral:
    type: str | None

@dataclass
class IntLiteral(NumberLiteral):
    value: int

@dataclass
class FloatLiteral(NumberLiteral):
    value: float

def pad(indent: int) -> str:
    return "  " * indent

def fmt_sem(node: AstNode):
    return f" : {node.sem_type}" if getattr(node, "sem_type", None) is not None else ""

class AstNode:
    sem_type: Any | None

    def __init__(self):
        self.sem_type = None        # resolved type (after semantic analysis)

    def format(self, indent: int = 0) -> str:
        raise NotImplementedError

# =========================
# EXPRESSIONS
# =========================

class Expr(AstNode):
    pass

@dataclass
class NumberExpr(Expr):
    value: NumberLiteral
    type: Expr | None
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}NumberExpr({self.value.value}{fmt_sem(self)})"

@dataclass
class BoolExpr(Expr):
    value: bool
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}BoolExpr({self.value}{fmt_sem(self)})"


@dataclass
class StringExpr(Expr):
    value: str
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f'{pad(indent)}StringExpr("{self.value}"{fmt_sem(self)})'

class UnaryOp(Enum):
    NEG = "neg"
    NOT = "not"
    REF = "ref"
    DEREF = "deref"

    def __init__(self, op_name: str):
        self.op_name = op_name

@dataclass
class CastExpr(Expr):
    inner: Expr
    type: Expr

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}CastExpr({self.type}{fmt_sem(self)})\n"
            f"{self.inner.format(indent + 1)}"
        )

@dataclass
class UnaryExpr(Expr):
    inner: Expr
    op: UnaryOp
    
    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}UnaryExpr({self.op.name}{fmt_sem(self)})\n"
            f"{self.inner.format(indent + 1)}"
        )

class BinaryOp(Enum):
    CMP_EQ = "=="
    CMP_NE = "!="
    CMP_LT = "<"
    CMP_GT = ">"
    CMP_LE = "<="
    CMP_GE = ">="
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"

    def __init__(self, op_name: str):
        self.op_name = op_name
    
    def is_cmp(self):
        return self in [
            self.CMP_EQ,
            self.CMP_NE,
            self.CMP_LT,
            self.CMP_GT,
            self.CMP_LE,
            self.CMP_GE,
        ]

@dataclass
class BinaryExpr(Expr):
    left: Expr
    op: BinaryOp
    right: Expr

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}BinaryExpr({self.op.name}{fmt_sem(self)})\n"
            f"{self.left.format(indent + 1)}\n"
            f"{self.right.format(indent + 1)}"
        )
    
@dataclass
class CallExpr(Expr):
    callee: Expr
    args: list[tuple[str | None, Expr]]

    def format(self, indent: int = 0) -> str:
        if not self.args:
            args_str = f"{pad(indent + 1)}<no args>"
        else:
            args_str = "\n".join(
                f"{pad(indent + 1)}Arg({name})\n{expr.format(indent + 2)}"
                for name, expr in self.args
            )

        return (
            f"{pad(indent)}CallExpr{fmt_sem(self)}\n"
            f"{self.callee.format(indent + 1)}\n"
            f"{args_str}"
        )

@dataclass
class IdentifierExpr(Expr):
    name: str
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}IdentifierExpr({self.name}{fmt_sem(self)})"


@dataclass
class MemberExpr(Expr):
    owner: Expr
    name: str

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}MemberExpr({self.name}{fmt_sem(self)})\n"
            f"{self.owner.format(indent + 1)}"
        )


# =========================
# STATEMENTS
# =========================

class Stmt(AstNode):
    pass

@dataclass
class VarDeclStmt(Stmt):
    name: str
    type: Expr | None
    assign: Expr | None

    def format(self, indent: int = 0) -> str:
        type_str = self.type.format(indent + 1) if self.type else f"{pad(indent + 1)}<no type>"
        value_str = self.assign.format(indent + 1) if self.assign else f"{pad(indent + 1)}<no value>"

        return (
            f"{pad(indent)}VarDeclStmt({self.name}{fmt_sem(self)})\n"
            f"{pad(indent + 1)}Type:\n{type_str}\n"
            f"{pad(indent + 1)}Value:\n{value_str}"
        )

@dataclass
class AssignStmt(Stmt):
    target: Expr
    assign: Expr

    def format(self, indent: int = 0) -> str:
        return (
            f"{pad(indent)}AssignStmt{fmt_sem(self)}\n"
            f"{pad(indent + 1)}Target:\n"
            f"{self.target.format(indent + 2)}\n"
            f"{pad(indent + 1)}Value:\n"
            f"{self.assign.format(indent + 2)}"
        )

@dataclass
class ExprStmt(Stmt):
    expr: Expr

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}ExprStmt{fmt_sem(self)}\n{self.expr.format(indent + 1)}"


@dataclass
class ReturnStmt(Stmt):
    expr: Expr

    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}ReturnStmt{fmt_sem(self)}\n{self.expr.format(indent + 1)}"

@dataclass
class WhileStmt(Stmt):
    cond: Expr
    body: list[Stmt]
    
    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}WhileStmt{fmt_sem(self)}\n{pad(indent + 1)}Cond:\n{self.cond.format(indent + 2)}\n{pad(indent + 1)}Body:\n{"\n".join([stmt.format(indent + 2) for stmt in self.body])}"

@dataclass
class IfStmt(Stmt):
    cond: Expr
    body_if: list[Stmt]
    body_else: list[Stmt]
    
    def format(self, indent: int = 0) -> str:
        return f"{pad(indent)}IfStmt{fmt_sem(self)}\n{pad(indent + 1)}Cond:\n{self.cond.format(indent + 2)}\n{pad(indent + 1)}BodyIf:\n{"\n".join([stmt.format(indent + 2) for stmt in self.body_if])}\n{pad(indent + 1)}BodyElse:\n{"\n".join([stmt.format(indent + 2) for stmt in self.body_else])}"

# =========================
# MISC
# =========================

@dataclass
class Function(AstNode):
    ident: Ident
    name: str
    asm_name: str | None
    is_extern: bool
    is_inline: bool
    args: list[tuple[str | None, Expr]]
    ret_type: Expr | None
    body: list[Stmt]
    span: SourceSpan

    def format(self, indent: int = 0) -> str:
        args_str = "\n".join(
            f"{pad(indent + 2)}Arg({name if name else '_'}) : {typ.format(0)}"
            for name, typ in self.args
        ) or f"{pad(indent + 2)}<no args>"

        ret_str = self.ret_type.format(indent + 2) if self.ret_type else f"{pad(indent + 2)}<no return type>"
        body_str = "\n".join(stmt.format(indent + 2) for stmt in self.body) or f"{pad(indent + 2)}<empty body>"

        flags_str = ("extern" if self.is_extern else "") + (f" __asm__({self.asm_name})" if self.asm_name else "")

        return (
            f"{pad(indent)}Function({self.name}{fmt_sem(self)})\n"
            f"{pad(indent + 1)}Flags: {flags_str}\n"
            f"{pad(indent + 1)}Args:\n{args_str}\n"
            f"{pad(indent + 1)}ReturnType:\n{ret_str}\n"
            f"{pad(indent + 1)}Body:\n{body_str}"
        )

@dataclass
class Field(AstNode):
    name: str
    type: Expr
    init: Expr

    def format(self, indent: int = 0) -> str:
        type_str = self.type.format(indent + 2) if self.type else f"{pad(indent + 2)}<no type>"
        init_str = self.init.format(indent + 2) if self.init else f"{pad(indent + 2)}<no init>"

        return (
            f"{pad(indent)}Field({self.name}{fmt_sem(self)})\n"
            f"{pad(indent + 1)}Type:\n{type_str}\n"
            f"{pad(indent + 1)}Init:\n{init_str}"
        )

@dataclass
class Object(AstNode):
    ident: Ident
    name: str
    fields: list[Field]
    functions: list[Function]
    
    def format(self, indent: int = 0) -> str:
        functions_str = (
            "\n".join(f.format(indent + 2) for f in self.functions)
            if self.functions
            else f"{pad(indent + 2)}<no functions>"
        )

        fields_str = (
            "\n".join(f.format(indent + 2) for f in self.fields)
            if self.fields
            else f"{pad(indent + 2)}<no fields>"
        )

        return (
            f"{pad(indent)}Object({self.name}{fmt_sem(self)})\n"
            f"{pad(indent + 1)}Functions:\n{functions_str}\n"
            f"{pad(indent + 1)}Fields:\n{fields_str}"
        )

@dataclass
class Module(AstNode):
    ident: Ident
    curr_path: Path
    imports: dict[str, Path] # symbol -> path
    # TODO: refactor back to list[Function]
    functions: dict[str, Function] # symbol -> Function
    objects: list[Object]
    statements: list[Stmt]

    def format(self, indent: int = 0) -> str:
        imports_str = (
            "\n".join(f"{pad(indent + 2)} {s} -> {p}" for (s, p) in self.imports.items())
            if self.imports
            else f"{pad(indent + 2)}<no imports>"
        )

        functions_str = (
            "\n".join(f.format(indent + 2) for f in self.functions.values())
            if self.functions
            else f"{pad(indent + 2)}<no functions>"
        )
        
        objects_str = (
            "\n".join(f.format(indent + 2) for f in self.objects)
            if self.objects
            else f"{pad(indent + 2)}<no objects>"
        )

        statements_str = (
            "\n".join(s.format(indent + 2) for s in self.statements)
            if self.statements
            else f"{pad(indent + 2)}<no statements>"
        )

        return (
            f"{pad(indent)}Module({self.curr_path}):\n"
            f"{pad(indent + 1)}Imports:\n{imports_str}\n"
            f"{pad(indent + 1)}Objects:\n{objects_str}\n"
            f"{pad(indent + 1)}Functions:\n{functions_str}\n"
            f"{pad(indent + 1)}Statements:\n{statements_str}"
        )
from dataclasses import dataclass
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

@dataclass
class Ident:
    segs: list[str]

    def of(segs: str) -> Ident:
        return Ident(segs=segs.split("::"))

    def __str__(self) -> str:
        return "::".join(self.segs)
    
    def __hash__(self):
        return hash(tuple(self.segs))
    
    def sub(self, seg: str) -> Ident:
        return Ident(segs=self.segs+[seg])
    
    def subs(self, seg: str) -> str:
        return str(self) + "::" + seg

@dataclass
class SourceSpan:
    start_offset: int
    end_offset: int
    start_line: int
    start_col: int
    raw_text: str | None

    # col and line are indicies

    def combine(a: SourceSpan, b: SourceSpan) -> SourceSpan:
        return SourceSpan(
            raw_text=None,
            start_offset=min(a.start_offset, b.start_offset),
            end_offset=max(a.end_offset, b.end_offset),
            start_line=min(a.start_line, b.start_line),
            start_col=min(a.start_col, b.start_col),
        )
    
    def len(self):
        return self.end_offset - self.start_offset
    
    def __repr__(self):
        return f"Ln {self.start_line + 1}, Col {self.start_col + 1} ({self.len()})"
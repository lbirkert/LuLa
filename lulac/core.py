from dataclasses import dataclass

@dataclass
class SourceSpan:
    start_offset: int
    end_offset: int
    start_line: int
    start_col: int
    raw_text: str | None

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
        return f"Ln {self.start_line}, Col {self.start_col} ({self.len()})"
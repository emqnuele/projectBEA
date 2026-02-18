import textwrap
from typing import List, Tuple, Optional

def fit_text_for_box(
    message: str,
    *,
    line_width: int,
    max_lines: Optional[int],
    base_font_size: int,
    min_font_size: int,
    font_step: int,
) -> Tuple[str, int]:
    """Restituisce testo wrappato e font che ci sta nel box."""
    safe_base = max(1, base_font_size)
    safe_min = max(1, min_font_size)
    safe_step = max(1, font_step)

    chosen_lines: List[str] = []
    chosen_size = safe_base
    chosen_width = line_width

    # se max_lines è none o <= 0, lo trattiamo come infinito
    allow_infinite = max_lines is None or max_lines <= 0

    for size in range(safe_base, safe_min - 1, -safe_step):
        width = max(1, int(round(line_width * safe_base / size)))
        wrapped = textwrap.wrap(message, width=width)
        if not wrapped:
            wrapped = [""]
        
        if allow_infinite or len(wrapped) <= max_lines:
            chosen_lines = wrapped
            chosen_size = size
            chosen_width = width
            break

    if not chosen_lines:
        chosen_size = safe_min
        chosen_width = max(1, int(round(line_width * safe_base / chosen_size)))
        chosen_lines = textwrap.wrap(message, width=chosen_width) or [""]

    if not allow_infinite and len(chosen_lines) > max_lines:
        chosen_lines = chosen_lines[:max_lines]
        last = chosen_lines[-1]
        ellipsis = "..."
        if len(last) + len(ellipsis) > chosen_width:
            last = last[: max(0, chosen_width - len(ellipsis))]
        chosen_lines[-1] = f"{last}{ellipsis}"

    return "\n".join(chosen_lines), chosen_size

def paginate_text_for_box(
    message: str,
    *,
    line_width: int,
    max_lines: Optional[int],
    base_font_size: int,
    min_font_size: int,
    font_step: int
) -> Tuple[List[str], int]:
    """
    splits text into multiple pages (chunks) trying to respect sentence boundaries.
    returns: (List[page_text], font_size_used)
    """
    import re

    target_size = base_font_size
    target_width = max(1, line_width)
    clean_message = message.replace("\n", " ").strip()
    token = "||||"
    temp = re.sub(r'([.!?])\s+', r'\1' + token, clean_message)
    raw_sentences = temp.split(token)
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    
    if not sentences:
        sentences = [clean_message]

    pages = []
    current_page_sentences = []
    
    def measure_lines(text_chunk):
        w = textwrap.wrap(text_chunk, width=target_width)
        return len(w) if w else 0

    if max_lines is None or max_lines <= 0:
        return ["\n".join(textwrap.wrap(message, width=target_width))], target_size

    for sent in sentences:
        # try adding to current page
        candidate_list = current_page_sentences + [sent]
        candidate_text = " ".join(candidate_list)
        
        if measure_lines(candidate_text) <= max_lines:
            current_page_sentences.append(sent)
        else:
            # if current page has content, flush it
            if current_page_sentences:
                pages.append("\n".join(textwrap.wrap(" ".join(current_page_sentences), width=target_width)))
                current_page_sentences = []

            # now handle the new sentence
            if measure_lines(sent) <= max_lines:
                current_page_sentences.append(sent)
            else:
                # big sentence, must chunk
                wrapped_sent = textwrap.wrap(sent, width=target_width)
                # chunk list of lines
                for i in range(0, len(wrapped_sent), max_lines):
                    chunk = wrapped_sent[i:i + max_lines]
                    pages.append("\n".join(chunk))
                # current_sentences remains empty as we fully flushed this big sentence

    if current_page_sentences:
        pages.append("\n".join(textwrap.wrap(" ".join(current_page_sentences), width=target_width)))
        
    return pages, target_size

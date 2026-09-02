#!/usr/bin/env python3
"""코드 파일에 한글로 된 이름이 들어갔는지 센다.

보칙은 코드에 속하는 것을 프로젝트 관례대로, 관례가 없으면 영문으로 쓰라고 정한다.
식별자와 딕셔너리 키와 열거형 값과 파일명이 여기 해당한다.
반면 주석과 사람에게 보이는 메시지는 한국어로 쓴다.

그래서 검사 전에 주석과 문자열 리터럴을 지우고, 남은 코드에서만 한글을 찾는다.
지우는 일을 대충 하면 한국어 주석이 통째로 위반으로 잡혀 훅을 꺼 버리게 된다.
그래서 놓치는 쪽을 택했다. 문자열 안의 한글은 세지 않으므로 한글 딕셔너리 키는
이 검사에 걸리지 않는다. 오탐으로 신뢰를 잃는 것보다 낫다고 봤다.

사용법:
    ko_identifier_check.py [파일]
종료 코드: 위반이 없으면 0, 있으면 1.

반환 구조의 키는 영문이다. 다른 도구가 파싱하는 인터페이스이기 때문이다.
"""
import io
import json
import os
import re
import sys
import tokenize

C_LINE = ("//",)
C_BLOCK = (("/*", "*/"),)


def _profile(line=(), block=(), triples=(), quotes="\"'",
             template="", interp=True, str_interp=False, verbatim_at=False,
             raw_hash=False, markup=False, regex=False):
    return {
        "line": tuple(line),
        "block": tuple(block),
        "triples": tuple(triples),
        "quotes": quotes,
        "template": template,
        "interp": interp,
        "str_interp": str_interp,
        "verbatim_at": verbatim_at,
        "raw_hash": raw_hash,
        "markup": markup,
        "regex": regex,
    }


PROFILES = {
    "python": _profile(line=("#",), triples=('"""', "'''")),
    "js": _profile(line=C_LINE, block=C_BLOCK, quotes="\"'`",
                   template="`", regex=True),
    "jsx": _profile(line=C_LINE, block=C_BLOCK + (("<!--", "-->"),),
                    quotes="\"'`", template="`", regex=True, markup=True),
    "c": _profile(line=C_LINE, block=C_BLOCK, str_interp=True),
    "csharp": _profile(line=C_LINE, block=C_BLOCK, triples=('"""',),
                       verbatim_at=True),
    "go": _profile(line=C_LINE, block=C_BLOCK, quotes="\"'`", template="`", interp=False),
    "rust": _profile(line=C_LINE, block=C_BLOCK, raw_hash=True),
    "php": _profile(line=C_LINE + ("#",), block=C_BLOCK),
    "ruby": _profile(line=("#",), block=(("=begin", "=end"),)),
    "sql": _profile(line=("--",), block=C_BLOCK),
}

EXT_LANG = {
    ".py": "python", ".pyi": "python",
    ".js": "js", ".mjs": "js", ".cjs": "js", ".ts": "js",
    ".jsx": "jsx", ".tsx": "jsx", ".vue": "jsx", ".svelte": "jsx",
    ".java": "c", ".kt": "c", ".kts": "c", ".scala": "c", ".groovy": "c",
    ".c": "c", ".h": "c", ".cpp": "c", ".hpp": "c", ".cc": "c", ".hh": "c",
    ".m": "c", ".mm": "c", ".swift": "c", ".dart": "c",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".sql": "sql",
}

# 이름에 쓰이는 문자만 모은다. 한글이 하나라도 섞이면 잡는다.
IDENT = re.compile(r"[0-9A-Za-z_$가-힣ㄱ-ㅎㅏ-ㅣ]*[가-힣ㄱ-ㅎㅏ-ㅣ]"
                   r"[0-9A-Za-z_$가-힣ㄱ-ㅎㅏ-ㅣ]*")

# 정규식 문자 범위는 이름이 아니다. 예: [가-힣]
CHAR_RANGE = re.compile(r"[가-힣]\s*-\s*[가-힣]")

HANGUL = re.compile(r"[가-힣]")


def _blank(text: str) -> str:
    """행 번호를 지키려고 개행만 남기고 공백으로 바꾼다."""
    return "".join(c if c == "\n" else " " for c in text)


def _scan_string(text: str, start: int, quote: str,
                 verbatim: bool, interp: bool = False) -> int:
    """문자열 리터럴의 끝 위치를 찾는다.

    다트와 코틀린은 문자열 안 ${} 에 또 문자열을 넣는다.
    보간 구간을 건너뛰지 않으면 안쪽 따옴표를 종료로 읽어 짝이 밀리고,
    그 뒤의 평범한 코드가 문자열로 지워진다.

    따옴표 짝이 맞지 않는 코드에서 파일 끝까지 삼키지 않도록,
    여러 줄을 허용하지 않는 문자열은 줄 끝에서 닫힌 것으로 본다.
    """
    n = len(text)
    i = start + 1
    while i < n:
        ch = text[i]
        if not verbatim and ch == "\\":
            i += 2
            continue
        if interp and ch == "$" and i + 1 < n and text[i + 1] == "{":
            depth = 1
            i += 2
            while i < n and depth:
                c = text[i]
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                elif c == "\n":
                    break
                elif c in "\"'":
                    i = _scan_string(text, i, c, False, interp)
                    continue
                i += 1
            continue
        if ch == quote:
            if verbatim and i + 1 < n and text[i + 1] == quote:
                i += 2
                continue
            return i + 1
        if ch == "\n" and not verbatim:
            return i
        i += 1
    return n


def _scan_template(text: str, start: int, interp: bool) -> int:
    """백틱 문자열의 끝을 찾는다.

    자바스크립트는 ${} 안에 또 백틱 문자열을 넣을 수 있다.
    중괄호 깊이를 세지 않으면 안쪽 백틱을 종료로 잘못 읽어,
    그 뒤의 평범한 코드가 문자열로 지워지거나 그 반대가 된다.
    """
    n = len(text)
    i = start + 1
    depth = 0
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if interp and ch == "$" and i + 1 < n and text[i + 1] == "{":
            depth += 1
            i += 2
            continue
        if depth > 0:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == "`":
                i = _scan_template(text, i, interp)
                continue
            i += 1
            continue
        if ch == "`":
            return i + 1
        i += 1
    return n


# 중괄호 앞에 이것들이 오면 코드 블록이거나 객체 리터럴이다.
CODE_BEFORE_BRACE = set(")=,(;[{&|?")
BLOCK_WORDS = {"else", "try", "do", "return", "finally", "catch", "new"}

# 나눗셈이 아니라 정규식 리터럴이 올 수 있는 자리를 가린다.
CODE_WORDS = {
    "const", "let", "var", "return", "export", "import", "function", "class",
    "if", "else", "for", "while", "switch", "case", "default", "type",
    "interface", "enum", "await", "async", "new", "throw", "try", "catch",
    "finally", "do", "public", "private", "protected", "static", "yield",
}
REGEX_PREFIX = set("(,=:[!&|?{};+-*%<>~^")
REGEX_WORDS = {"return", "typeof", "case", "in", "of", "do", "else",
               "yield", "await", "new", "delete", "void"}


def _regex_allowed(text: str, i: int) -> bool:
    # 정규식은 공백으로 시작하지 않는다. 공백을 찾을 때도 \s 를 쓴다.
    # 화면 글 사이에 홀로 놓인 빗금을 정규식으로 읽으면 뒤쪽을 통째로 삼킨다.
    if i + 1 < len(text) and text[i + 1] in " \t":
        return False
    j = i - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] == "\n":
        return True
    # JSX 닫는 태그의 </ 를 정규식 시작으로 읽으면 뒤쪽 코드를 통째로 삼킨다.
    if text[j] == "<":
        return False
    if text[j] in REGEX_PREFIX:
        return True
    m = re.search(r"[A-Za-z_$]+$", text[max(0, j - 15):j + 1])
    return bool(m and m.group(0) in REGEX_WORDS)


def _scan_regex(text: str, start: int):
    """정규식 리터럴의 끝을 찾는다. 한 줄 안에서 닫히지 않으면 포기한다."""
    n = len(text)
    i = start + 1
    in_class = False
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "\n":
            return None
        if in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == "/":
            return i + 1
        i += 1
    return None


def _scan_raw_hash(text: str, start: int):
    """러스트의 r"..." 와 r#"..."# 를 처리한다."""
    n = len(text)
    i = start + 1
    hashes = 0
    while i < n and text[i] == "#":
        hashes += 1
        i += 1
    if i >= n or text[i] != '"':
        return None
    closer = '"' + "#" * hashes
    end = text.find(closer, i + 1)
    return n if end < 0 else end + len(closer)


def _mask_generic(text: str, prof: dict) -> str:
    out = []
    i, n = 0, len(text)
    while i < n:
        matched = False

        for start, end in prof["block"]:
            if text.startswith(start, i):
                j = text.find(end, i + len(start))
                j = n if j < 0 else j + len(end)
                out.append(_blank(text[i:j]))
                i = j
                matched = True
                break
        if matched:
            continue

        for token in prof["line"]:
            if text.startswith(token, i):
                j = text.find("\n", i)
                j = n if j < 0 else j
                out.append(_blank(text[i:j]))
                i = j
                matched = True
                break
        if matched:
            continue

        for triple in prof["triples"]:
            if text.startswith(triple, i):
                j = text.find(triple, i + len(triple))
                j = n if j < 0 else j + len(triple)
                out.append(_blank(text[i:j]))
                i = j
                matched = True
                break
        if matched:
            continue

        if prof["raw_hash"] and text[i] == "r":
            j = _scan_raw_hash(text, i)
            if j is not None:
                out.append(_blank(text[i:j]))
                i = j
                continue

        ch = text[i]

        if prof["regex"] and ch == "/" and _regex_allowed(text, i):
            j = _scan_regex(text, i)
            if j is not None:
                out.append(_blank(text[i:j]))
                i = j
                continue

        if prof["template"] and ch == prof["template"]:
            j = _scan_template(text, i, prof["interp"])
            out.append(_blank(text[i:j]))
            i = j
            continue

        if ch in prof["quotes"]:
            verbatim = prof["verbatim_at"] and i > 0 and text[i - 1] == "@"
            j = _scan_string(text, i, ch, verbatim, prof["str_interp"])
            out.append(_blank(text[i:j]))
            i = j
            continue

        out.append(ch)
        i += 1
    return "".join(out)


def _mask_python(text: str):
    """파이썬은 표준 토크나이저로 지운다. 문법이 깨져 있으면 None 을 낸다."""
    lines = text.splitlines(keepends=True)
    kinds = {tokenize.STRING, tokenize.COMMENT}
    for name in ("FSTRING_MIDDLE",):
        extra = getattr(tokenize, name, None)
        if extra is not None:
            kinds.add(extra)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except Exception:
        return None
    for tok in tokens:
        if tok.type not in kinds:
            continue
        (sr, sc), (er, ec) = tok.start, tok.end
        for row in range(sr, er + 1):
            if row - 1 >= len(lines):
                break
            line = lines[row - 1]
            a = sc if row == sr else 0
            b = ec if row == er else len(line)
            lines[row - 1] = line[:a] + _blank(line[a:b]) + line[b:]
    return "".join(lines)


def _text_before(text: str, k: int) -> bool:
    """이 자리 앞이 화면 글인지 본다.

    글 안에서 괄호를 열었다면 그 앞은 글자이거나 태그의 끝이거나 줄의 처음이다.
    코드에서 괄호를 열었다면 그 앞에 이름이나 닫는 괄호가 붙어 있다.
    """
    j = k - 1
    while j >= 0 and text[j] in " \t":
        j -= 1
    if j < 0 or text[j] == "\n":
        return True
    return bool(HANGUL.match(text[j]) or text[j] == ">")


def _text_continues(text: str, k: int) -> bool:
    """다음 줄이 앞줄의 화면 글에 이어지는지 본다.

    한글로 시작하고 코드의 기호가 없는 줄만 같은 글로 본다.
    코드 블록의 끝을 표현식의 끝으로 잘못 읽었을 때
    뒤따르는 코드까지 지워 거기 있는 한글 이름을 놓치는 일을 막는다.
    """
    while k < len(text) and text[k] in " \t":
        k += 1
    if k >= len(text):
        return False
    end = text.find("\n", k)
    line = text[k:end if end >= 0 else len(text)]
    if not HANGUL.search(line) or line[0] in "});":
        return False
    word = re.match(r"[0-9A-Za-z_$가-힣]+", line)
    if word is None or word.group(0) in CODE_WORDS:
        return False
    # 이름 뒤에 대입이나 호출이나 속성이 붙으면 코드다.
    return not re.match(r"\s*[=(]|\.[A-Za-z_$가-힣]", line[word.end():])


def _tag_open_at(text: str, i: int, pairs: dict) -> int:
    """이 꺾쇠가 태그의 끝이면 짝이 되는 여는 꺾쇠의 자리를 준다.

    뒤로 훑어 여는 꺾쇠를 먼저 만나야 태그이고, 태그가 아니면 -1을 준다.
    닫는 꺾쇠를 먼저 만나면 앞선 태그가 이미 닫힌 자리이므로 태그가 아니다.
    다만 화살표 함수와 크거나같음의 꺾쇠는 속성 안에 흔히 놓이므로 지나친다.
    속성값으로 준 중괄호 안에는 완결된 태그가 통째로 들어앉는 일이 잦으므로,
    닫는 중괄호를 만나면 짝이 되는 여는 중괄호까지 건너뛴다.
    """
    n = len(text)
    j = i - 1
    breaks = 0
    while j >= 0:
        c = text[j]
        if c == "}":
            op = pairs.get(j)
            if op is None:
                return -1
            j = op - 1
            continue
        if c == ">":
            arrow = j and text[j - 1] in "=-"
            ge = j + 1 < n and text[j + 1] == "="
            if arrow or ge:
                j -= 1
                continue
            return -1
        if c == "<":
            nxt = text[j + 1] if j + 1 < n else ""
            if nxt.isalpha() or nxt in "/>_$":
                return j
            # 속성 안에 놓인 크다작다 비교이므로 지나친다.
            j -= 1
            continue
        if c == "\n":
            breaks += 1
            if breaks > 20:
                return -1
        j -= 1
    return -1


def _mask_markup(text: str) -> str:
    """태그 사이에 놓인 한국어를 지운다.

    화면에 보이는 글이라 규칙의 대상이 아닌데 코드처럼 벌거벗고 있어서,
    지우지 않으면 화면 글자가 전부 위반으로 잡힌다.

    글의 시작은 여는 태그의 끝이거나 {expr} 표현식의 끝이고,
    글의 끝은 다음 태그이거나 다음 표현식이다.
    표현식 안에 또 태그가 들어앉는 일이 잦으므로 안쪽을 건너뛰지 않는다.
    건너뛰면 그 안의 글이 검사도 마스킹도 받지 못한 채 남는다.

    닫는 중괄호는 코드 블록의 끝이기도 하다. 짝이 되는 여는 중괄호를 찾아
    그 앞이 태그의 끝이나 글자일 때만 표현식으로 인정한다.
    코드 블록으로 읽고 그 뒤를 지우면 평범한 코드가 사라져,
    거기 있는 한글 이름을 놓친다.
    """
    chars = list(text)
    n = len(text)

    pairs = {}
    stack = []
    for idx, c in enumerate(text):
        if c == "{":
            stack.append(idx)
        elif c == "}" and stack:
            pairs[idx] = stack.pop()

    def wipe(a: int, b: int) -> None:
        if a >= b or not HANGUL.search(text[a:b]):
            return
        for k in range(a, b):
            if chars[k] != "\n":
                chars[k] = " "

    def is_expr_close(i: int) -> bool:
        j = pairs.get(i)
        if j is None:
            return False
        k = j - 1
        while k >= 0 and text[k] in " \t\n":
            k -= 1
        if k < 0:
            return False
        c = text[k]
        if c == ">":
            # 화살표 뒤의 중괄호는 함수 본문이다.
            return not (k and text[k - 1] in "=-")
        if c == ":":
            # 객체의 값 자리인지, 글 안의 쌍점인지 앞 글자로 가른다.
            return bool(k and HANGUL.search(text[k - 1]))
        if c == "(":
            # 글 안에 괄호를 열고 값을 끼워 넣는 문장이 흔하다.
            return _text_before(text, k)
        if c == "=":
            # 속성은 이름에 바로 붙지만 글 안의 등호는 앞이 비어 있다.
            return bool(k and text[k - 1] in " \t")
        if c in CODE_BEFORE_BRACE:
            return False
        word = re.search(r"[A-Za-z_$]+$", text[max(0, k - 15):k + 1])
        return not (word and word.group(0) in BLOCK_WORDS)

    i = 0
    while i < n:
        c = text[i]
        opens_text = False
        # 줄이 바뀌면 글이 끝난 것으로 볼 자리인지 함께 정한다.
        # 코드 블록의 끝이나 화면 글의 끝을 잘못 읽었을 때
        # 뒤따르는 코드까지 지우면 거기 있는 한글 이름을 놓치기 때문이다.
        one_line = False
        if c == ">" and not (i and text[i - 1] in "=->"):
            k = _tag_open_at(text, i, pairs)
            if k >= 0:
                opens_text = True
                # 여는 태그 뒤의 글은 여러 줄에 걸치지만,
                # 닫는 태그와 홀로 닫는 태그 뒤는 코드로 돌아가는 자리가 많다.
                one_line = text[k + 1] == "/" or text[i - 1] == "/"
        elif c == "}" and is_expr_close(i):
            opens_text = True
            one_line = True
        if not opens_text:
            i += 1
            continue
        j = i + 1
        # 뒤따르는 태그의 끝을 삼키지 않도록 꺾쇠에서도 끊고 다시 판정한다.
        while j < n:
            ch = text[j]
            if ch in "<{>}":
                break
            if ch == "\n" and one_line and not _text_continues(text, j + 1):
                break
            j += 1
        # 끝을 못 찾고 파일 끝에 닿았다면 화면 글이 아니다.
        # 화면 글이라면 닫는 태그가 반드시 뒤따른다.
        if j < n:
            wipe(i + 1, j)
        i = j if j > i else i + 1
    return "".join(chars)


# 사람이 손으로 쓴 소스는 이 크기를 넘지 않는다.
# 넘는 파일은 번들이나 생성물이라 검사할 이름이 없고,
# 한 줄로 뭉친 5메가짜리를 훑으면 편집마다 몇 초씩 붙는다.
MAX_BYTES = 1_000_000


def masked_code(text: str, ext: str):
    lang = EXT_LANG.get(ext.lower())
    if lang is None:
        return None
    if len(text) > MAX_BYTES:
        return None
    prof = PROFILES[lang]
    body = _mask_python(text) if lang == "python" else None
    if body is None:
        body = _mask_generic(text, prof)
    if prof["markup"]:
        body = _mask_markup(body)
    return CHAR_RANGE.sub(lambda m: _blank(m.group(0)), body)


def check(text: str, path: str) -> dict:
    ext = os.path.splitext(path)[1]
    body = masked_code(text, ext)
    hits = []
    if body is not None:
        for no, line in enumerate(body.split("\n"), 1):
            for m in IDENT.finditer(line):
                hits.append({"line": no, "name": m.group(0)})

    name = os.path.basename(path)
    filename_hangul = bool(body is not None and HANGUL.search(name))

    return {
        "supported": body is not None,
        "hits": hits,
        "filename_hangul": filename_hangul,
        "filename": name,
        "passed": not hits and not filename_hangul,
    }


def format_report(result: dict) -> str:
    lines = ["코드에 한글로 된 이름"]
    if result["filename_hangul"]:
        lines.append(f"  파일명: {result['filename']}")
    seen = set()
    for hit in result["hits"]:
        key = hit["name"]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  {hit['line']}행: {hit['name']}")
        if len(seen) >= 12:
            lines.append("  ...")
            break
    return "\n".join(lines)


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv

    if not args:
        print("검사할 파일 경로가 필요합니다. 확장자로 언어를 가리기 때문입니다.",
              file=sys.stderr)
        return 2

    path = args[0]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    result = check(text, path)

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 1

    if not result["supported"]:
        print("검사 대상 언어가 아닙니다.")
        return 0
    if result["passed"]:
        print("한글로 된 이름 없음")
        return 0

    print(format_report(result))
    return 1


if __name__ == "__main__":
    sys.exit(main())

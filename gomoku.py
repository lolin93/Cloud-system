BOARD_SIZE = 15
EMPTY = "."
PLAYER = "X"
AI = "O"


def create_board(size=BOARD_SIZE):
    return [[EMPTY for _ in range(size)] for _ in range(size)]


def get_valid_moves(board):
    return [
        (row_index, col_index)
        for row_index, row in enumerate(board)
        for col_index, cell in enumerate(row)
        if cell == EMPTY
    ]


def make_move(board, row, col, piece):
    if not is_inside(board, row, col):
        raise ValueError("Move is outside the board.")
    if board[row][col] != EMPTY:
        raise ValueError("Cell is already occupied.")

    new_board = [line[:] for line in board]
    new_board[row][col] = piece
    return new_board


def is_inside(board, row, col):
    return 0 <= row < len(board) and 0 <= col < len(board[row])


def check_winner(board, piece):
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))

    for row in range(len(board)):
        for col in range(len(board[row])):
            if board[row][col] != piece:
                continue

            for row_step, col_step in directions:
                if count_line(board, row, col, row_step, col_step, piece) >= 5:
                    return True

    return False


def count_line(board, row, col, row_step, col_step, piece):
    count = 0

    while is_inside(board, row, col) and board[row][col] == piece:
        count += 1
        row += row_step
        col += col_step

    return count


def is_full(board):
    return all(cell != EMPTY for row in board for cell in row)


def generate_candidate_moves(board, limit=60):
    valid_moves = get_valid_moves(board)
    if not valid_moves:
        return []

    occupied = [
        (row_index, col_index)
        for row_index, row in enumerate(board)
        for col_index, cell in enumerate(row)
        if cell != EMPTY
    ]
    center = len(board) // 2

    if not occupied:
        return [(center, center)]

    nearby_moves = []
    for move in valid_moves:
        row, col = move
        distance_to_piece = min(
            abs(row - piece_row) + abs(col - piece_col)
            for piece_row, piece_col in occupied
        )

        if distance_to_piece <= 4:
            nearby_moves.append(move)

    candidates = nearby_moves or valid_moves
    candidates.sort(
        key=lambda move: (
            min(
                abs(move[0] - piece_row) + abs(move[1] - piece_col)
                for piece_row, piece_col in occupied
            ),
            abs(move[0] - center) + abs(move[1] - center),
        )
    )
    return candidates[:limit]


def split_candidates(candidates, worker_count):
    return [
        candidates[index::worker_count]
        for index in range(worker_count)
    ]


WIN_SCORE = 10_000_000
BLOCK_WIN_SCORE = 9_000_000
SEARCH_DEPTH = 3
SEARCH_WIDTH = 16
DOUBLE_THREAT_SCORE = 3_000_000
FORCING_THREAT_SCORE = 700_000


def score_move(board, row, col):
    if board[row][col] != EMPTY:
        return -1_000_000

    ai_board = make_move(board, row, col, AI)
    if check_winner(ai_board, AI):
        return WIN_SCORE

    player_board = make_move(board, row, col, PLAYER)
    if check_winner(player_board, PLAYER):
        return BLOCK_WIN_SCORE + evaluate_board(ai_board)

    ai_threats = threat_space_score(ai_board, AI)
    player_threats = threat_space_score(ai_board, PLAYER)

    return minimax(
        ai_board,
        SEARCH_DEPTH,
        maximizing=False,
        alpha=-WIN_SCORE,
        beta=WIN_SCORE,
    ) + ai_threats - int(player_threats * 1.3)


def minimax(board, depth, maximizing, alpha, beta):
    if check_winner(board, AI):
        return WIN_SCORE + depth
    if check_winner(board, PLAYER):
        return -WIN_SCORE - depth
    if depth == 0 or is_full(board):
        return evaluate_board(board)

    piece = AI if maximizing else PLAYER
    candidates = generate_ordered_candidates(board, piece, SEARCH_WIDTH)

    if maximizing:
        value = -WIN_SCORE
        for row, col in candidates:
            value = max(
                value,
                minimax(make_move(board, row, col, AI), depth - 1, False, alpha, beta),
            )
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return value

    value = WIN_SCORE
    for row, col in candidates:
        value = min(
            value,
            minimax(make_move(board, row, col, PLAYER), depth - 1, True, alpha, beta),
        )
        beta = min(beta, value)
        if alpha >= beta:
            break
    return value


def generate_ordered_candidates(board, piece, limit):
    candidates = generate_candidate_moves(board, limit=limit * 2)
    candidates.sort(
        key=lambda move: quick_move_score(board, move[0], move[1], piece),
        reverse=True,
    )
    return candidates[:limit]


def quick_move_score(board, row, col, piece):
    if board[row][col] != EMPTY:
        return -WIN_SCORE

    board_after_move = make_move(board, row, col, piece)
    if check_winner(board_after_move, piece):
        return WIN_SCORE

    opponent = PLAYER if piece == AI else AI
    opponent_board = make_move(board, row, col, opponent)
    block_score = WIN_SCORE // 2 if check_winner(opponent_board, opponent) else 0
    return block_score + evaluate_move_lines(board_after_move, row, col, piece)


def threat_space_score(board, piece):
    opponent = PLAYER if piece == AI else AI
    winning_moves = find_winning_moves(board, piece)
    opponent_winning_moves = find_winning_moves(board, opponent)
    open_fours = 0
    closed_fours = 0
    open_threes = 0

    for row, col in generate_candidate_moves(board, limit=50):
        test_board = make_move(board, row, col, piece)
        threats = classify_move_threats(test_board, row, col, piece)
        open_fours += threats["open_four"]
        closed_fours += threats["closed_four"]
        open_threes += threats["open_three"]

    score = 0
    if len(winning_moves) >= 2:
        score += DOUBLE_THREAT_SCORE
    elif len(winning_moves) == 1:
        score += FORCING_THREAT_SCORE

    if len(opponent_winning_moves) >= 2:
        score -= DOUBLE_THREAT_SCORE
    elif len(opponent_winning_moves) == 1:
        score -= FORCING_THREAT_SCORE

    if open_fours >= 2:
        score += DOUBLE_THREAT_SCORE
    elif open_fours == 1:
        score += FORCING_THREAT_SCORE

    if closed_fours >= 2:
        score += DOUBLE_THREAT_SCORE // 2
    elif closed_fours == 1:
        score += 180_000

    if open_fours >= 1 and open_threes >= 1:
        score += DOUBLE_THREAT_SCORE
    elif open_threes >= 2:
        score += 900_000
    elif open_threes == 1:
        score += 120_000

    return score


def find_winning_moves(board, piece):
    winning_moves = []

    for row, col in generate_candidate_moves(board, limit=50):
        if check_winner(make_move(board, row, col, piece), piece):
            winning_moves.append((row, col))

    return winning_moves


def classify_move_threats(board, row, col, piece):
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))
    threats = {
        "open_four": 0,
        "closed_four": 0,
        "open_three": 0,
    }

    for row_step, col_step in directions:
        length = 1
        length += count_direction(board, row, col, row_step, col_step, piece)
        length += count_direction(board, row, col, -row_step, -col_step, piece)
        open_ends = count_open_ends(board, row, col, row_step, col_step, piece)

        if length >= 4 and open_ends == 2:
            threats["open_four"] += 1
        elif length >= 4 and open_ends == 1:
            threats["closed_four"] += 1
        elif length == 3 and open_ends == 2:
            threats["open_three"] += 1

    return threats


def evaluate_board(board):
    return evaluate_piece(board, AI) - int(evaluate_piece(board, PLAYER) * 1.2)


def evaluate_piece(board, piece):
    total = 0
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))

    for row in range(len(board)):
        for col in range(len(board[row])):
            if board[row][col] != piece:
                continue

            for row_step, col_step in directions:
                prev_row = row - row_step
                prev_col = col - col_step
                if is_inside(board, prev_row, prev_col) and board[prev_row][prev_col] == piece:
                    continue

                length, open_ends = analyze_line(board, row, col, row_step, col_step, piece)
                total += pattern_score(length, open_ends)

    return total


def analyze_line(board, row, col, row_step, col_step, piece):
    length = 0
    current_row = row
    current_col = col

    while is_inside(board, current_row, current_col) and board[current_row][current_col] == piece:
        length += 1
        current_row += row_step
        current_col += col_step

    open_ends = 0
    if is_inside(board, current_row, current_col) and board[current_row][current_col] == EMPTY:
        open_ends += 1

    before_row = row - row_step
    before_col = col - col_step
    if is_inside(board, before_row, before_col) and board[before_row][before_col] == EMPTY:
        open_ends += 1

    return length, open_ends


def pattern_score(length, open_ends):
    if length >= 5:
        return WIN_SCORE
    if length == 4 and open_ends == 2:
        return 1_000_000
    if length == 4 and open_ends == 1:
        return 120_000
    if length == 3 and open_ends == 2:
        return 60_000
    if length == 3 and open_ends == 1:
        return 8_000
    if length == 2 and open_ends == 2:
        return 2_000
    if length == 2 and open_ends == 1:
        return 300
    if length == 1 and open_ends == 2:
        return 30
    return 1


def evaluate_move_lines(board, row, col, piece):
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))
    total = 0

    for row_step, col_step in directions:
        line_length = 1
        line_length += count_direction(board, row, col, row_step, col_step, piece)
        line_length += count_direction(board, row, col, -row_step, -col_step, piece)
        open_ends = count_open_ends(board, row, col, row_step, col_step, piece)
        total += pattern_score(line_length, open_ends)

    center = len(board) // 2
    total += 100 - (abs(row - center) + abs(col - center))
    return total


def count_open_ends(board, row, col, row_step, col_step, piece):
    open_ends = 0

    next_row = row + row_step
    next_col = col + col_step
    while is_inside(board, next_row, next_col) and board[next_row][next_col] == piece:
        next_row += row_step
        next_col += col_step
    if is_inside(board, next_row, next_col) and board[next_row][next_col] == EMPTY:
        open_ends += 1

    prev_row = row - row_step
    prev_col = col - col_step
    while is_inside(board, prev_row, prev_col) and board[prev_row][prev_col] == piece:
        prev_row -= row_step
        prev_col -= col_step
    if is_inside(board, prev_row, prev_col) and board[prev_row][prev_col] == EMPTY:
        open_ends += 1

    return open_ends


def evaluate_lines(board, row, col, piece):
    directions = ((1, 0), (0, 1), (1, 1), (1, -1))
    total = 0

    for row_step, col_step in directions:
        line_length = 1
        line_length += count_direction(board, row, col, row_step, col_step, piece)
        line_length += count_direction(board, row, col, -row_step, -col_step, piece)
        total += line_length * line_length

    return total


def count_direction(board, row, col, row_step, col_step, piece):
    count = 0
    row += row_step
    col += col_step

    while is_inside(board, row, col) and board[row][col] == piece:
        count += 1
        row += row_step
        col += col_step

    return count


def choose_ai_move(board):
    candidates = generate_candidate_moves(board)
    if not candidates:
        return None

    return max(candidates, key=lambda move: score_move(board, move[0], move[1]))

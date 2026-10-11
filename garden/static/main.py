from flask import Flask, request, jsonify, session
from flask_cors import CORS
import sqlite3
import cshogi
import random
from typing import Optional, List
import os
import uuid
import threading
import time

app = Flask(__name__,
            static_folder='static',
            static_url_path='/static')
CORS(app)

DB_PATH = os.environ.get('DATABASE_PATH', 'shogi.db')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def cleanup_old_moves():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM game_moves
            WHERE created_at < datetime('now', '-4 hours')
              AND id NOT IN (
                  SELECT id FROM (
                      SELECT id FROM game_moves ORDER BY id ASC LIMIT 10
                  )
              )
        """)
        conn.commit()
        print(f"Cleanup: deleted {cur.rowcount} old moves")
    except Exception as e:
        print(f"Cleanup error: {e}")
    finally:
        conn.close()

def cleanup_loop():
    while True:
        time.sleep(3600)
        cleanup_old_moves()

@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

class Game:
    def __init__(self, user_id=None):
        self.user_id = user_id
        self.board = cshogi.Board()
        self.game_over = False
        if user_id:
            self.load_moves_from_db()

    def load_moves_from_db(self):
        if not self.user_id:
            return

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT move FROM game_moves
                WHERE user_id = ?
                ORDER BY created_at ASC
            """, (self.user_id,))

            moves = cur.fetchall()
            moves = [{'move': row[0]} for row in moves]

            for move_record in moves:
                try:
                    move = self.board.move_from_usi(move_record['move'])
                    self.board.push(move)
                except Exception as e:
                    print(f"Error loading move {move_record['move']}: {e}")
        finally:
            conn.close()

    def save_move_to_db(self, move_usi):
        if not self.user_id:
            return

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                INSERT INTO game_moves (user_id, move, created_at)
                VALUES ('{self.user_id}', '{move_usi}', datetime('now'))
            """)
            conn.commit()
        finally:
            conn.close()

    def clear_game_from_db(self):
        if not self.user_id:
            return

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM game_moves
                WHERE user_id = ?
            """, (self.user_id,))
            conn.commit()
        finally:
            conn.close()

    def get_state(self):
        try:
            legal_moves = [cshogi.move_to_usi(move) for move in self.board.legal_moves]
        except Exception as e:
            print(f"Error getting legal moves: {e}")
            legal_moves = []
        current_player = cshogi.BLACK if self.board.turn == cshogi.BLACK else cshogi.WHITE
        try:
            black_hand = self.board.pieces_in_hand[cshogi.BLACK]
            white_hand = self.board.pieces_in_hand[cshogi.WHITE]
            captured_black = {i+1: count for i, count in enumerate(black_hand) if count > 0}
            captured_white = {i+1: count for i, count in enumerate(white_hand) if count > 0}
            captured_black = {i+1: count for i, count in enumerate(black_hand) if count > 0}
            captured_white = {i+1: count for i, count in enumerate(white_hand) if count > 0}
        except Exception as e:
            print(f"Error converting captured pieces: {e}")
            captured_black = {}
            captured_white = {}

        is_game_over = self.board.is_game_over()
        is_check = self.board.is_check()

        return {
            "sfen": self.board.sfen(),
            "legal_moves": legal_moves,
            "is_check": is_check,
            "is_checkmate": is_game_over and is_check,
            "is_stalemate": is_game_over and not is_check,
            "turn": "black" if self.board.turn == cshogi.BLACK else "white",
            "captured_pieces": {
                "black": captured_black,
                "white": captured_white
            }
        }

    def generate_drop_moves(self, color):
        drop_moves = []
        captured_list = self.board.pieces_in_hand[color]
        captured = {i+1: count for i, count in enumerate(captured_list) if count > 0}
        captured = {i+1: count for i, count in enumerate(captured_list) if count > 0}

        for piece_type, count in captured.items():
            if count > 0:
                piece_symbol = self.get_drop_piece_symbol(piece_type, color)
                test_squares = ['5e', '4d', '6f', '3c', '7g']
                for square in test_squares:
                    drop_moves.append(f"{piece_symbol}*{square}")

        return drop_moves

    def get_drop_piece_symbol(self, piece_type, color):
        symbols = {
            cshogi.PAWN: 'P',
            cshogi.LANCE: 'L',
            cshogi.KNIGHT: 'N',
            cshogi.SILVER: 'S',
            cshogi.GOLD: 'G',
            cshogi.BISHOP: 'B',
            cshogi.ROOK: 'R'
        }
        return symbols.get(piece_type, '?')

    def get_piece_type_from_symbol(self, symbol):
        symbol_to_type = {
            'P': cshogi.PAWN,
            'L': cshogi.LANCE,
            'N': cshogi.KNIGHT,
            'S': cshogi.SILVER,
            'G': cshogi.GOLD,
            'B': cshogi.BISHOP,
            'R': cshogi.ROOK
        }
        return symbol_to_type.get(symbol, 0)

    def is_square_empty(self, square):
        sfen = self.board.sfen()
        board_part = sfen.split(' ')[0]
        rows = board_part.split('/')
        file = square[0]
        rank = square[1]
        row_names = 'abcdefghi'
        col_names = '123456789'
        row_idx = row_names.index(rank)
        col_idx = col_names.index(file)
        if row_idx >= len(rows):
            return True
        row = rows[row_idx]
        col_pos = 0
        for char in row:
            if char.isdigit():
                col_pos += int(char)
            elif col_pos == col_idx:
                return False
            else:
                col_pos += 1
        return True

    def make_move(self, move_usi: str) -> bool:
        try:
            move = self.board.move_from_usi(move_usi)
            if move == 0:
                print(f"{move_usi=} {move=}")
                raise ValueError("Invalid move")
            if '*' in move_usi:
                current_player = cshogi.BLACK if self.board.turn == cshogi.BLACK else cshogi.WHITE
                piece_symbol = move_usi[0]
                piece_type = self.get_piece_type_from_symbol(piece_symbol)
                hand_index = piece_type - 1
                if hand_index >= len(self.board.pieces_in_hand[current_player]) or self.board.pieces_in_hand[current_player][hand_index] <= 0:
                    return False
                if not self.is_valid_drop(move, current_player):
                    return False
            else:
                if move not in self.board.legal_moves:
                    return False
            self.board.push(move)

            return True
        except (ValueError, Exception) as e:
            print(f"Move error: {e}")
            return False

    def is_valid_drop(self, move, color):
        return True

    def ai_move(self) -> Optional[str]:
        legal_moves = list(self.board.legal_moves)
        if not legal_moves:
            return None
        best_move = None
        best_score = -float('inf')
        for move in legal_moves:
            self.board.push(move)
            score = self.evaluate_position()
            self.board.pop()

            if score > best_score:
                best_score = score
                best_move = move

        if best_move:
            self.board.push(best_move)
            return cshogi.move_to_usi(best_move)
        move = random.choice(legal_moves)
        self.board.push(move)
        return cshogi.move_to_usi(move)

    def evaluate_position(self) -> float:
        score = 0
        piece_values = {
            cshogi.PAWN: 1,
            cshogi.LANCE: 3,
            cshogi.KNIGHT: 4,
            cshogi.SILVER: 5,
            cshogi.GOLD: 6,
            cshogi.BISHOP: 8,
            cshogi.ROOK: 10,
            cshogi.KING: 100
        }
        white_hand = self.board.pieces_in_hand[cshogi.WHITE]
        black_hand = self.board.pieces_in_hand[cshogi.BLACK]
        white_captured_value = sum(count * piece_values.get(piece_type, 0)
                                  for piece_type, count in enumerate(white_hand) if count > 0)
        black_captured_value = sum(count * piece_values.get(piece_type, 0)
                                  for piece_type, count in enumerate(black_hand) if count > 0)
        score = white_captured_value - black_captured_value
        if self.board.is_check():
            score += 5
        if self.board.is_game_over() and self.board.is_check():
            score += 1000
        return score

def get_or_create_user_session():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

@app.route("/game/state", methods=["GET"])
def get_game_state():
    user_id = get_or_create_user_session()
    game = Game(user_id)
    return jsonify(game.get_state())

@app.route("/game/move", methods=["POST"])
def make_move():
    user_id = get_or_create_user_session()
    game = Game(user_id)

    if game.game_over:
        return jsonify({"error": "Game is over"}), 400

    data = request.get_json()
    if not data or 'move' not in data:
        return jsonify({"error": "Move required"}), 400

    player_move = data['move']
    success = game.make_move(player_move)
    if not success:
        return jsonify({"error": "Invalid move"}), 400
    game.save_move_to_db(player_move)
    moves_made = [player_move]
    state = game.get_state()
    if not (state['is_checkmate'] or state['is_stalemate']) and state['turn'] == 'white':
        ai_move_result = game.ai_move()
        if ai_move_result:
            game.save_move_to_db(ai_move_result)
            moves_made.append(ai_move_result)
            state = game.get_state()
    if state['is_checkmate'] or state['is_stalemate']:
        game.game_over = True
    state['moves_made'] = moves_made
    return jsonify(state)

@app.route("/game/new", methods=["POST"])
def new_game():
    user_id = get_or_create_user_session()
    game = Game(user_id)
    game.clear_game_from_db()
    return jsonify({"message": "New game started"})

if __name__ == "__main__":
    threading.Thread(target=cleanup_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8001, debug=True)

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from configparser import ConfigParser, ExtendedInterpolation
from datetime import datetime, timedelta
import socket
import time
import re
import os
import numpy as np
import pandas as pd
import PySimpleGUI as sg
import random
from pathlib import Path
import shutil
from chess import Move, Board

chrome_path = r"C:\Users\isaac\Anaconda3\pkgs\python-chromedriver-binary-75.0.3770.8.0-py37_0\Lib\site-packages\chromedriver_binary\chromedriver.exe"
firefox_path = r"C:\Users\isaac\human\geckodriver.exe"


# TODO: Use WebDriverWait instead of sleep :D
# TODO: Make timeout a decorator\
# TODO Question whether it is really OK to abuse boolean conversion everywhere
class Turk:
    def __init__(self, v):
        # Options
        self.verbose = v
        # Ints
        self.vote_time_int = 18
        self.vote_time_grain = .001  # 1/grain is the number of ways the timer can be displayed
        # Bools
        self.game_over = False
        self.white = None
        # Lists
        self.moves_list = []
        self.black_dims = {'a': 8, 'b': 7, 'c': 6, 'd': 5, 'e': 4, 'f': 3, 'g': 2, 'h': 1}
        # Internal counts
        self.board_half_moves = 0

        # Selenium
        self.username = "SuperJames_90"
        self.browser = None
        self.css = {"input": "input[class='ready']", "moves_area": "div[class='rmoves']", "status": "p[class='status']",
                    "login": "a[href='/login?referrer=/']", "user": "input[name='username']",
                    "pass": "input[name='password']",
                    "ai": "a[href='/setup/ai']", "button_white": "button[value='white']",
                    "orientation_b": "div[class='cg-wrap orientation-black manipulable']",
                    "orientation_w": "div[class='cg-wrap orientation-white manipulable']"}
        # Stream
        self.pic_path = "pics"
        self.w_pics = ["chars_white.png", "nums_white.png"]
        self.b_pics = ["chars_black.png", "nums_black.png"]
        self.pics_targets = ["chars_obs.png", "nums_obs.png"]
        # GUI
        self.chat_window_location = (-474, 736)
        self.votes_window_location = (-1863, 171)
        self.timer_window_location = (-276, 672)
        # IRC Config
        self.config = ConfigParser(interpolation=ExtendedInterpolation())
        self.config.read("secrets.ini")
        default = self.config["DEFAULTS"]
        self.server = default["server"]
        self.port = int(default["port"])
        self.nickname = default["nickname"]
        self.token = default["token"]
        self.channel = default["channel"]
        self.players_path = default["player_path"]

        # Create socket
        self.sock = socket.socket()

        # Board
        self.board = Board()

        # RE (match moves)
        self.matcher = re.compile("[a-h][1-8][a-h][1-8]")

        # GUI
        # Votes Graph/Window
        self.graph_size = (342, 400)
        self.graph_bl = (0, 500)
        self.graph_tr = (500, 0)

        graph = sg.Graph(self.graph_size, self.graph_bl, self.graph_tr, background_color="#FFFFFF", pad=(0, 0),
                         key="graph")
        self.votes_window = sg.Window("Votes", [[graph]], location=self.votes_window_location, element_padding=(0, 0),
                                      background_color="#FFFFFF",
                                      no_titlebar=True, keep_on_top=True, grab_anywhere=True)
        self.votes_window.Finalize()
        # Timer window
        self.timer_size = (200, 50)
        self.timer_bl = (0, 0)
        self.timer_tr = self.timer_size

        timer_graph = sg.Graph(self.timer_size, self.timer_bl, self.timer_tr,
                               background_color="#EDEBE9", pad=(0, 0), key="timer_graph")
        self.timer_window = sg.Window("Timer", [[timer_graph]], location=self.timer_window_location,
                                      element_padding=(0, 0), margins=(0, 0),
                                      background_color="#EDEBE9", no_titlebar=True, keep_on_top=True,
                                      grab_anywhere=True)

        self.timer_window.Finalize()

        # Chat window
        chat_text = sg.Text(" \n" * 10, size=(33, 10), font="Roboto 16", background_color="#FFFFFF",
                            justification="right", pad=(0, 0), key=f"chat")

        chat_layout = [[chat_text]]
        self.chat_window = sg.Window("Chat", chat_layout, location=self.chat_window_location, element_padding=(0, 0),
                                     background_color="#FFFFFF", no_titlebar=True, keep_on_top=True, grab_anywhere=True)
        self.chat_window.Finalize()

        # DATA
        if not os.path.exists(self.players_path):
            pd.DataFrame(columns=["id", "move", "pre_move", "count"]).to_csv(self.players_path, index=False)
        self.data = pd.read_csv(self.players_path)
        self.data.drop(list(self.data.filter(regex="Unnamed")), axis=1, inplace=True)
        # Tracking
        self.update_counts = {}

    ######
    # Setup
    ######
    def start_browser(self):
        # Start browser
        self.browser = webdriver.Firefox(executable_path=firefox_path)
        self.browser.set_window_position(-1000, 0)
        self.browser.maximize_window()
        "We have to manually hit F11 for now, not working in current version for firefox."
        self.browser.get("https://lichess.org/")
        time.sleep(2)

    # Assume browser exists
    def signin(self):
        self.handle_element_by_css_selector(self.css['login'], 15, click=True)
        time.sleep(3)
        self.handle_element_by_css_selector(self.css["user"], 15, keys=self.config["DEFAULTS"]["user"])
        self.handle_element_by_css_selector(self.css["pass"], 15, keys=self.config["DEFAULTS"]["pass"] + Keys.RETURN)
        time.sleep(3)

    # Assumes signed in
    def start_computer_game(self):
        print("Starting computer game", flush=True)
        self.handle_element_by_css_selector(self.css["ai"], 15, click=True)
        time.sleep(3)
        self.handle_element_by_css_selector(self.css["button_white"], 15, click=True)
        time.sleep(3)
        return True

    #######
    # Socket
    #######
    # Assumes Socket is init
    def connect(self):
        try:
            self.sock.connect((self.server, self.port))
        except OSError:
            return
        self.sock.settimeout(10)
        self.sock.send(f"PASS {self.token}\n".encode("utf-8"))
        self.sock.send(f"NICK {self.nickname}\n".encode("utf-8"))
        self.sock.send(f"JOIN {self.channel}\n".encode("utf-8"))
        # Just cleaning up the intro messages
        for i in range(3):
            self.skip_next_msg()
        self.sock.settimeout(False)

    # Try to send ping but it doesnt work right now
    def ping(self):
        self.sock.send(f"PING".encode("utf-8"))
        back = ""
        while True:
            try:
                back = self.sock.recv(2048).decode("utf-8")
            except:
                pass
            if "PONG" in back:
                print(back, flush=True)

    # Don"t parse the next message but still handle
    def skip_next_msg(self):
        try:
            self.sock.recv(2048).decode("utf-8")
            return True
        except BlockingIOError:
            print("hit error", flush=True)
            time.sleep(3)
            return self.skip_next_msg()

    def parse_next_msg(self):
        # If we get a ping handle it and get next message
        try:
            in_str = (self.sock.recv(2048).decode("utf-8"))
        except BlockingIOError:
            return False
        # Handle disconnect
        if len(in_str) == 0:
            self.connect()
            return self.parse_next_msg()
        # Handle PING
        if in_str[0:4] == "PING":
            self.sock.send(f"PONG\n".encode("utf-8"))
            print("PING PONG", flush=True)
            return self.parse_next_msg()
        # Get user and msg from string
        user = in_str[1:in_str.find("!")]
        msg = str.rstrip(in_str[in_str.find(":", 30, len(in_str)) + 1:])
        if self.verbose:
            out = f"{user} -> {msg}"
            if len(out) == 4:
                print(type(user), flush=True)
                print(type(msg), flush=True)
            print(f"{user} -> {msg}", flush=True)
        # Check if it"s a move
        if len(msg) == 5 and msg[0] == "-":
            msg = msg[1:]
            pre_move = True
        else:
            pre_move = False

        if len(msg) == 4 and self.matcher.match(msg):
            # Try to get existing entry
            # https://stackoverflow.com/questions/46621712/add-a-new-row-to-a-pandas-dataframe-with-specific-index-name
            if user in self.data["id"].values:
                # old = self.data.loc[self.data["id"] == user]
                if pre_move:
                    self.data.loc[self.data["id"] == user, "pre_move"] = msg
                else:
                    self.data.loc[self.data["id"] == user, "move"] = msg
                self.data.loc[self.data["id"] == user, "count"] += 1
            else:
                if pre_move:
                    pm = msg
                    m = None
                else:
                    pm = "N/A"
                    m = msg
                # self.data = pd.concat([self.data, pd.DataFrame([[m, pm, 1]], columns = ["move", "pre_move", "count"]], ignore_index = True))
                self.data.loc[len(self.data)] = [user, m, pm, 1]
            self.update_chat_window(f"{user} -> {msg}")
            return True

    ###############
    # Selenium/Board
    ###############
    def handle_element_by_css_selector(self, css_selector: str, timeout, click=False, keys=None, sub_selector=None,
                                       get=False):
        # Lots of possible functionality
        # a) click an element and/or send keys to that element
        # b) click an child element and/or send keys to that child element
        # c) get an element (want to avoid this, want to handle everything with element references in this function hopefully)
        # Example selector: "p[class='status']"
        if sub_selector:
            if click or keys:
                raise Exception

        max_time = timedelta(seconds=timeout)
        start = datetime.now()
        while True:
            try:
                ele = self.browser.find_element_by_css_selector(css_selector)
                if sub_selector:
                    ele = ele.find_element_by_css_selector(sub_selector)
                if click:
                    ele.click()
                    click = False
                if keys:
                    ele.send_keys(keys)
                    keys = None
                if get:
                    return ele
                return True
            except(NoSuchElementException, StaleElementReferenceException):
                if datetime.now() - start > max_time:
                    break
                time.sleep(.1)
                continue
        return False

    def handle_moves_list(self, timeout=10, returning='list'):
        # Return either the list of moves (strings) or a count of moves (int)
        moves = []
        max_time = timedelta(seconds=timeout)
        start = datetime.now()
        while True:
            try:
                elements = self.handle_element_by_css_selector(self.css["moves_area"], timeout,
                                                               get=True).find_elements_by_css_selector("m2")
                if returning == 'len':
                    return len(elements)
                for el in elements:
                    moves.append(el.text)
                return moves
            except(NoSuchElementException, StaleElementReferenceException):
                if datetime.now() - start > max_time:
                    break
                time.sleep(.1)
                continue
        return False

    # Functions that assume context: We are in a signed in chess game.
    def is_white(self):
        t = 0
        while t < 3:
            if self.handle_element_by_css_selector(self.css["orientation_b"], timeout=t):
                self.white = False
                return False
            if self.handle_element_by_css_selector(self.css["orientation_w"], timeout=t):
                self.white = True
                return True
            t += 1
        raise Exception

    def our_turn(self):
        # Odd # moves -> Blacks turn. Even # Moves -> Whites turn
        if self.handle_moves_list(returning='len') % 2 != self.is_white():
            print("Our turn", flush=True)
            return True
        else:
            print("Not our turn", flush=True)
            return False

    def get_legal_ucis(self):
        out = []
        for i in self.board.legal_moves:
            out.append(Move.uci(i))
        return out

    def decide_premove(self):
        ####
        # Choose to premove if:
        # 1) A majority of players want to premove (ANY premove)
        # 2) The highest voted premove is valid (don"t defer downwards in popularity like in decide_move)
        ####
        legal = self.get_legal_ucis()
        # This loop should only iterate through the first two items
        # The reason this is a loop despite the context, we avoid having to try/catch keyerrors
        result = None
        for move, ratio in self.data["pre_move"].value_counts(normalize=True).items():
            print(f"move: {move} ratio: {ratio}", flush=True)
            if move == "NA":
                if ratio > .5:
                    break
                else:
                    continue
            if move in legal:
                result = move
            else:
                break
        # Reset votes (Don"t set it to none, like in decide_move, because we do want to count it)
        self.data["pre_move"] = "N/A"
        return result

    def decide_move(self):
        legal = self.get_legal_ucis()
        for move, ratio in self.data["move"].value_counts(normalize=True).items():
            if move in legal:
                self.data["move"] = None
                self.update_votes_window()
                return move
        # Reset votes
        self.data["move"] = None
        self.update_votes_window()
        # No legal moves voted for, randomly move
        self.update_chat_window("(Took a randomized move)")
        return random.choice(legal)

    def update_status(self):
        # 0/False: Nothing was updated
        # 1/True: Updated moveslist
        # 2: Game ended
        print("update status", flush=True)
        if self.handle_element_by_css_selector(self.css["status"], 0):
            self.game_over = True
            return 2
        # Using css element references outside of handle function
        out = self.handle_moves_list()
        if len(out) - len(self.moves_list) < 0:
            print("Somehow moves_list got longer than the actual moves list on the site.", flush=True)
            raise Exception
        if len(out) - len(self.moves_list) == 0:
            print("Didn't add moves", flush=True)
            # if len(out) == 0:
            #     return True
            return False

        diff = len(out) - len(self.moves_list)
        if diff in self.update_counts:
            self.update_counts[diff] += 1
        else:
            self.update_counts[diff] = 1
        for i in range(diff, 0, -1):
            print("Need to add moves", flush=True)
            move = self.board.uci(self.board.parse_san(out[-i]))
            self.board.push_uci(move)
            self.moves_list.append(move)
            self.board_half_moves += 1
            return True

    def uci_to_offset(self, uci, l):
        # Get board
        # Convert uci to four ints
        coords = [self.black_dims[uci[0]], int(uci[1]),
                  self.black_dims[uci[2]], int(uci[3])]
        if self.is_white():
            coords = [9 - x for x in coords]
        # e2e4 is now 5254 (if white) or 4244 (if black)
        # Now get pixel offset
        return [(x * 2 - 1) * l for x in coords]

    def move(self, uci):
        # While true with break so we skip first check
        for i in range(50):
            print(".", flush=True)
            board = self.handle_element_by_css_selector("cg-board", 0, get=True)
            incr = board.size['width'] / 16
            offsets = self.uci_to_offset(uci, incr)
            # Use offsets
            action = ActionChains(self.browser)
            action.move_to_element_with_offset(board, offsets[0], offsets[1])
            action.click_and_hold()
            action.move_to_element_with_offset(board, offsets[2], offsets[3])
            action.release()
            action.perform()
            status = self.update_status()
            if status == 1 or status == 2:
                print(" -Done!", flush=True)
                return
        print("ERROR")
        raise Exception

    def edit_name(self):
        # lichess detects this as a js script call and boots our ip address. Use with caution.
        while True:
            try:
                names = self.browser.find_elements_by_xpath(f"//*[contains(text(), {self.username})]")
                print(f"found {len(names)} names", flush=True)
                assert (len(names) == 4)
                for name in names:
                    self.browser.execute_script("arguments[0].innerText = 'Twitch Chat level 1'", name)
                return True
            except(NoSuchElementException, StaleElementReferenceException, AssertionError):
                print("Couldn't find all 4 names. Trying again in 2 seconds.")
                time.sleep(2)

    def rematch(self):
        time.sleep(5)
        start = datetime.now()
        self.handle_element_by_css_selector("button[class^='fbt rematch']", 5, click=True)
        time.sleep(5)
        # self.edit_name()
        self.is_white()
        self.update_board_labels()
        self.game_over = False
        self.moves_list = []
        self.board_half_moves = 0
        self.board = Board()
        end = datetime.now()
        print(end - start)
        time.sleep(5)

    #######
    # Stream
    #######
    def update_votes_window(self):
        # Graph vars
        max_w = int(self.graph_tr[0] * .85)
        separator = 2
        width = int(max_w - 9 * separator) / 10
        # Color vars (A RGB value has to be >16 since handling hex(<16) is not important enough to take up lines)
        rgb_start = (230, 240, 249)
        rgb_end = (40, 97, 249)
        rgb_lin = [np.linspace(rgb_start[0], rgb_end[0], max_w + 1).astype(int),
                   np.linspace(rgb_start[1], rgb_end[1], max_w + 1).astype(int),
                   np.linspace(rgb_start[2], rgb_end[2], max_w + 1).astype(int)]
        # Get graph and reset (erase)
        graph = self.votes_window.Element("graph")
        graph.Erase()
        # Iterate through the list of moves and their ratios
        ratio_series = self.data["move"].value_counts(normalize=True)
        for i in range(min(len(ratio_series), 10)):
            ratio = ratio_series.iloc[i]
            bar_val = int(ratio * max_w)
            hex_color = f"#{hex(rgb_lin[0][bar_val])[2:]}{hex(rgb_lin[1][bar_val])[2:]}{hex(rgb_lin[2][bar_val])[2:]}"
            y = i * (width + separator)
            graph.DrawRectangle(top_left=(0, y),
                                bottom_right=(bar_val, y + width),
                                fill_color=hex_color, line_color=hex_color)
            graph.DrawText(text=ratio_series.index[i], location=(max_w * 0.15, y + (width * .5)),
                           font="Roboto 18")
            graph.DrawText(text=f"{round(ratio * 100, 2)}%", location=(max_w * 1.1, y + (width * .5)),
                           font="Roboto 10")
        self.votes_window.Read(timeout=10)
        return True

    def update_timer_window(self, delta: float):
        # Graph vars
        width = self.timer_tr[0]
        height = self.timer_tr[1]
        # Color vars
        hex_color = "#72A33A"
        # Get graph and reset (erase)
        timer = self.timer_window.Element("timer_graph")
        timer.Erase()
        ratio = 1 - (delta / self.vote_time_int)
        rounded = round(ratio / self.vote_time_grain) * self.vote_time_grain
        x = rounded * width
        timer.DrawRectangle(top_left=(0, 0),
                            bottom_right=(x, height),
                            fill_color=hex_color, line_color=hex_color)
        self.timer_window.Read(timeout=10)
        return True

    def update_board_labels(self):
        # check if all files are present
        base = Path.cwd() / self.pic_path
        for fp in self.w_pics + self.b_pics:
            if not (base / fp).exists():
                print(f"picture missing: {fp}", flush=True)
                raise Exception
        # rename into the obs files (overwriting)
        if self.is_white():
            shutil.copy(base / self.w_pics[0], base / self.pics_targets[0])
            shutil.copy(base / self.w_pics[1], base / self.pics_targets[1])
        else:
            shutil.copy(base / self.b_pics[0], base / self.pics_targets[0])
            shutil.copy(base / self.b_pics[1], base / self.pics_targets[1])
        return

    def update_chat_window(self, chat):
        # start
        chat_el = self.chat_window.Element("chat")
        chats = chat_el.DisplayText.splitlines()[1:]
        chats.append(chat)
        # Update and read
        chat_el.Update(value='\n'.join(chats), font="Roboto 16")
        self.chat_window.Read(timeout=0)
        return

    ######
    # TEST
    ######

    def test_colors(self):
        print("Testing colors", flush=True)
        separator = 2
        max_w = self.graph_tr[0]
        width = int(max_w - 9 * separator) / 10
        rgb_start = (230, 240, 249)
        rgb_end = (16, 98, 219)
        rgb_lin = [np.linspace(rgb_start[0], rgb_end[0], max_w + 1).astype(int),
                   np.linspace(rgb_start[1], rgb_end[1], max_w + 1).astype(int),
                   np.linspace(rgb_start[2], rgb_end[2], max_w + 1).astype(int)]
        graph = self.votes_window.Element("graph")
        graph.Erase()
        for i in range(int(max_w / 10)):
            bar_val = (i + 1) * 10
            y = i * (width + separator)
            hex_color = f"#{hex(rgb_lin[0][bar_val])[2:]}{hex(rgb_lin[1][bar_val])[2:]}{hex(rgb_lin[2][bar_val])[2:]}"
            print(hex_color, flush=True)
            graph.DrawRectangle(top_left=(0, y),
                                bottom_right=(bar_val, y + width),
                                fill_color=hex_color, line_color=hex_color)
            graph.DrawText(text=f"{bar_val / 100}%", location=(max_w * 0.5, y + (width * .5)),
                           font="Roboto 20")
            self.votes_window.Read(timeout=10)
        return True

    def test_timer(self):
        # Draw line from bl to tr
        timer = self.timer_window.Element("timer_graph")
        timer.Erase()
        timer.DrawLine((0, 0), (self.timer_tr[0], 0), width=5)
        self.timer_window.Read(timeout=10)
        time.sleep(3)
        # Try timing
        vote_time = timedelta(seconds=self.vote_time_int)
        start = datetime.now()
        print(f"Start testing timer. Waiting for {self.vote_time_int}", flush=True)
        while (datetime.now() - start) < vote_time:
            self.update_timer_window((datetime.now() - start).total_seconds() * 100)
            time.sleep(1)
        self.update_timer_window(vote_time.seconds)
        return True

    def test_coords(self):
        self.connect()
        # Selenium
        self.start_browser()
        self.start_computer_game()
        return

    #####
    # DATA
    #####
    def write_csv(self):
        self.data.to_csv(self.players_path)

    # MAIN
    def run(self):
        print("Running", flush=True)
        # Socket
        self.connect()
        # Selenium
        self.start_browser()
        # self.start_computer_game()
        self.update_timer_window(0)
        input("Start a game and then press any key to continue")
        vote_time = timedelta(seconds=self.vote_time_int)
        self.update_votes_window()
        # *Setup stream*
        time.sleep(1)
        self.is_white()
        self.update_board_labels()
        self.data["move"] = None
        # Get locations
        print(f"chat_window location: {self.chat_window.CurrentLocation()}")
        print(f"votes_window location: {self.votes_window.CurrentLocation()}")
        print(f"timer_window location: {self.timer_window.CurrentLocation()}")
        while True:
            while not self.our_turn() and not self.game_over:
                if not self.parse_next_msg():
                    # Do other things in the meantime like update stream text
                    self.update_votes_window()
                    time.sleep(.1)
                    self.update_status()

            self.update_status()
            # Update with what move opponent made
            if self.game_over:
                print("Game ended!\n\n", flush=True)
                self.rematch()
                continue
            # Possible premove
            choice = self.decide_premove()
            if choice is not None:
                print("Premoving", flush=True)
                self.move(choice)
                continue
            # Our turn
            start = datetime.now()
            print(f"Start our turn. Listening for {self.vote_time_int}", flush=True)
            while (datetime.now() - start) < vote_time:
                if not self.parse_next_msg():
                    self.update_votes_window()
                    self.update_timer_window((datetime.now() - start).total_seconds())
            self.update_timer_window(vote_time.seconds)
            self.update_chat_window("_" * 33)
            # Decide winning move
            self.move(self.decide_move())
        return


if __name__ == "__main__":
    test = Turk(True)
    try:
        test.run()
    except Exception as e:
        raise e
    finally:
        test.write_csv()

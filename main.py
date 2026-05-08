import sys        # 處理系統參數
import os         # 處理檔案系統
import time       # 處理時間
import socket     # TCP 網路通訊
import threading  # 多執行緒
import hashlib    # SHA-256 hash

STORAGE_DIR = "/storage"  # 區塊資料存放資料夾

if not os.path.exists(STORAGE_DIR):  # 如果資料夾不存在
    os.makedirs(STORAGE_DIR)         # 建立資料夾


def get_hash(filepath):
    """計算檔案 SHA-256 hash"""

    if not os.path.exists(filepath):  # 如果檔案不存在
        return "MISSING"

    with open(filepath, 'rb') as f:   # 用二進位讀取檔案
        return hashlib.sha256(f.read()).hexdigest()  # 回傳 hash


class P2PLedger:

    def __init__(self, my_ip, peers):
        self.my_ip = my_ip              # 自己的 IP
        self.peers = peers              # 其他 Docker 節點
        self.port = 8001                # 固定 port
        self.mempool = []               # 尚未打包進區塊的交易
        self.seen_tx = set()            # 已看過的交易 ID，避免重複
        self.remote_hashes = {}         # 存其他節點 hash 資訊

    def get_last_block_id(self):
        """取得目前最後一個區塊編號"""

        files = [f for f in os.listdir(STORAGE_DIR) if f.endswith('.txt')]  # 找所有 txt 區塊檔

        if not files:  # 如果沒有任何區塊
            return 0

        return max([int(f.split('.')[0]) for f in files])  # 回傳最大編號

    def get_balance(self, user):
        """掃描所有區塊，計算某個使用者餘額"""

        balance = 0  # 初始餘額

        for i in range(1, self.get_last_block_id() + 1):  # 從第 1 個區塊掃到最後一個
            path = f"{STORAGE_DIR}/{i}.txt"  # 區塊檔案路徑

            if os.path.exists(path):  # 如果區塊存在
                with open(path, 'r') as f:  # 開啟區塊
                    for line in f:  # 逐行讀取
                        if line.startswith("TX:"):  # 只處理交易行
                            data = line.replace("TX:", "").strip().split(",")  # 拆交易內容

                            s = data[0]              # sender，付款人
                            r = data[1]              # receiver，收款人
                            amt = float(data[2])     # 金額
                            fee = float(data[3])     # 手續費

                            if s == user:            # 如果 user 是付款人
                                balance -= (amt + fee)  # 扣掉金額加手續費

                            if r == user:            # 如果 user 是收款人
                                balance += amt       # 增加金額

        return balance  # 回傳餘額

    def get_all_block_hashes(self):
        """取得本機所有區塊 hash，用於 checkall"""

        hashes = {}  # 存放格式：{區塊編號: hash}

        last_id = self.get_last_block_id()  # 取得最後區塊編號

        for i in range(1, last_id + 1):  # 掃描所有區塊
            path = f"{STORAGE_DIR}/{i}.txt"  # 區塊路徑

            if os.path.exists(path):  # 如果區塊存在
                hashes[i] = get_hash(path)  # 存 hash
            else:
                hashes[i] = "MISSING"  # 缺失標記

        return hashes  # 回傳所有 hash

    def get_all_block_data(self):
        """取得本機所有區塊完整內容，用於 checkchain 自癒"""

        data = {}  # 存放格式：{區塊編號: {"hash": hash, "content": content}}

        last_id = self.get_last_block_id()  # 取得最後區塊編號

        for i in range(1, last_id + 1):  # 掃描所有區塊
            path = f"{STORAGE_DIR}/{i}.txt"  # 區塊檔案路徑

            if os.path.exists(path):  # 如果區塊存在
                with open(path, 'r') as f:  # 開啟檔案
                    content = f.read()  # 讀取完整內容

                h = hashlib.sha256(content.encode()).hexdigest()  # 算內容 hash

                data[i] = {  # 存該區塊資料
                    "hash": h,
                    "content": content
                }

        return data  # 回傳所有區塊資料

    def broadcast(self, msg):
        """廣播訊息給所有 peer"""

        for peer_ip, peer_port in self.peers:  # 對每個 peer 傳送
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # 建立 TCP socket
                    s.settimeout(0.5)  # 設定 timeout，避免卡住
                    s.connect((peer_ip, peer_port))  # 連線到 peer
                    s.sendall(msg.encode())  # 傳送訊息
            except:
                pass  # 如果連線失敗就忽略

    def listen(self):
        """監聽其他 Docker 節點傳來的訊息"""

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # 建立 TCP server
            s.bind((self.my_ip, self.port))  # 綁定自己的 IP 與 port
            s.listen()  # 開始監聽

            while True:
                conn, addr = s.accept()  # 等待其他節點連進來

                with conn:
                    data = conn.recv(65535).decode()  # 接收訊息

                    if data.startswith("TX:"):  # 收到交易
                        tx_data = data.replace("TX:", "")  # 去掉 TX:
                        tx_id = tx_data.split(",")[-1]  # 取出交易 ID

                        if tx_id not in self.seen_tx:  # 如果沒看過這筆交易
                            self.mempool.append(tx_data)  # 放進交易池
                            self.seen_tx.add(tx_id)  # 記錄已看過

                    elif data.startswith("BLOCK:"):  # 收到新區塊
                        parts = data.split(" ", 2)  # 拆成 BLOCK:、區塊編號、區塊內容

                        with open(f"{STORAGE_DIR}/{parts[1]}.txt", 'w') as f:  # 建立區塊檔
                            f.write(parts[2])  # 寫入內容

                        print(f"\n[P2P] 收到新區塊 {parts[1]}，同步完成。")  # 顯示同步完成

                    elif data == "REQ_HASH":  # 對方要求最新區塊 hash
                        last_id = self.get_last_block_id()  # 找最新區塊
                        h = get_hash(f"{STORAGE_DIR}/{last_id}.txt")  # 算最新區塊 hash
                        conn.sendall(f"HASH {self.my_ip} {h}".encode())  # 回傳

                    elif data == "REQ_ALL_HASH":  # 對方要求所有區塊 hash
                        hashes = self.get_all_block_hashes()  # 取得所有 hash

                        body = "|".join(  # 組成 1:hash|2:hash|3:hash
                            [f"{block_id}:{h}" for block_id, h in hashes.items()]
                        )

                        conn.sendall(f"ALL_HASH {self.my_ip} {body}".encode())  # 回傳所有 hash

                    elif data == "REQ_ALL_BLOCKS":  # 對方要求所有區塊完整內容
                        blocks = self.get_all_block_data()  # 取得所有區塊資料

                        body = ""  # 用字串打包所有區塊

                        for block_id, info in blocks.items():  # 逐一處理每個區塊
                            safe_content = info["content"].replace("\n", "\\n")  # 把換行轉成 \n，避免傳輸拆壞
                            body += f"{block_id}::{info['hash']}::{safe_content}##"  # 打包格式

                        conn.sendall(f"ALL_BLOCKS {self.my_ip} {body}".encode())  # 回傳所有區塊內容

                    elif data.startswith("HASH "):  # 收到 hash 回覆
                        _, ip, h = data.split()  # 拆資料
                        self.remote_hashes[ip] = h  # 存起來

                    elif data.startswith("REQ_BLOCK"):  # 收到單一區塊修復請求
                        b_id = data.split()[1]  # 取得區塊編號

                        if os.path.exists(f"{STORAGE_DIR}/{b_id}.txt"):  # 如果本機有該區塊
                            with open(f"{STORAGE_DIR}/{b_id}.txt", 'r') as f:  # 開啟區塊
                                conn.sendall(f"BLOCK_DATA {b_id} {f.read()}".encode())  # 回傳區塊內容

                    elif data.startswith("BLOCK_DATA"):  # 收到單一區塊資料
                        parts = data.split(" ", 2)  # 拆成 BLOCK_DATA、區塊編號、內容
                        b_id = parts[1]  # 區塊編號
                        content = parts[2]  # 區塊內容

                        with open(f"{STORAGE_DIR}/{b_id}.txt", 'w') as f:  # 寫回本機
                            f.write(content)  # 寫入內容

                        print(f"\n[P2P] 區塊 {b_id} 修復完成。")  # 顯示修復完成

    def tx(self, sender, receiver, amount, fee):
        """建立交易並廣播"""

        if sender != "sys" and self.get_balance(sender) < (amount + fee):  # 檢查餘額是否足夠
            print(f"❌ 餘額不足！{sender} 無法支付 {amount + fee}")  # 顯示錯誤
            return  # 結束

        tx_id = hashlib.sha256(  # 產生交易 ID
            f"{sender}{receiver}{amount}{fee}{time.time()}".encode()
        ).hexdigest()[:8]

        tx_data = f"{sender},{receiver},{amount},{fee},{tx_id}"  # 組交易資料

        self.mempool.append(tx_data)  # 加入自己的交易池
        self.seen_tx.add(tx_id)  # 記錄交易 ID
        self.broadcast(f"TX:{tx_data}")  # 廣播交易

        print(f"✅ 交易已發布: {sender} -> {receiver} ({amount}) 手續費: {fee}")  # 顯示成功

    def mine(self):
        """挖礦產生新區塊"""

        if not self.mempool:  # 如果交易池是空的
            print("📭 獎池無交易，無法挖礦。")  # 顯示不能挖
            return

        last_id = self.get_last_block_id()  # 最新區塊 ID
        new_id = last_id + 1  # 新區塊 ID

        if last_id > 0:  # 如果之前有區塊
            prev_h = get_hash(f"{STORAGE_DIR}/{last_id}.txt")  # 取得前一區塊 hash
        else:
            prev_h = "0" * 64  # 第一個區塊前 hash 用 64 個 0

        fees = sum([float(t.split(",")[3]) for t in self.mempool])  # 加總手續費
        reward = 100 + fees  # 礦工獎勵
        reward_tx = f"TX:sys,{self.my_ip},{reward},0,REWARD_{new_id}"  # 獎勵交易

        print(f"挖礦中... 目標區塊: {new_id}, 預期獎勵: {reward}")  # 顯示挖礦資訊

        nonce = 0  # nonce 從 0 開始

        while True:
            content = f"Prev:{prev_h}\nNonce:{nonce}\n{reward_tx}\n"  # 區塊基本內容

            for t in self.mempool:  # 加入所有交易
                content += f"TX:{t}\n"

            h = hashlib.sha256(content.encode()).hexdigest()  # 計算區塊 hash

            if h.startswith("00"):  # 挖礦條件：hash 開頭為 00
                break  # 成功找到 nonce

            nonce += 1  # 繼續嘗試下一個 nonce

        with open(f"{STORAGE_DIR}/{new_id}.txt", 'w') as f:  # 建立新區塊檔
            f.write(content)  # 寫入區塊內容

        self.broadcast(f"BLOCK: {new_id} {content}")  # 廣播新區塊
        self.mempool = []  # 清空交易池

        print(f"🎉 挖礦成功！產生區塊 {new_id}。")  # 顯示成功

    def check_all_blocks(self):
        """checkall：比對三個 Docker 節點所有區塊 hash"""

        all_hashes = {}  # 存所有節點的 hash

        all_hashes[self.my_ip] = self.get_all_block_hashes()  # 先放自己的 hash

        for peer_ip, peer_port in self.peers:  # 問其他節點
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # 建立連線
                    s.settimeout(1)  # timeout
                    s.connect((peer_ip, peer_port))  # 連 peer
                    s.sendall("REQ_ALL_HASH".encode())  # 要求所有 hash

                    data = s.recv(65535).decode()  # 接收資料

                    if data.startswith("ALL_HASH"):  # 如果格式正確
                        parts = data.split(" ", 2)  # 拆資料
                        ip = parts[1]  # 節點 IP
                        body = parts[2] if len(parts) > 2 else ""  # 內容

                        hashes = {}  # 存該節點 hash

                        if body:  # 如果有內容
                            for item in body.split("|"):  # 拆每個 block
                                block_id, h = item.split(":", 1)  # 拆成 ID 和 hash
                                hashes[int(block_id)] = h  # 存入

                        all_hashes[ip] = hashes  # 存該節點所有 hash

            except:
                print(f"⚠️ 無法連線到節點 {peer_ip}")  # 連線失敗

        all_block_ids = set()  # 存所有出現過的區塊 ID

        for hashes in all_hashes.values():  # 掃每個節點
            all_block_ids.update(hashes.keys())  # 加入區塊 ID

        print("\n--- 三個 Docker 節點區塊比對 ---")  # 標題

        for block_id in sorted(all_block_ids):  # 逐一比對每個區塊
            print(f"\nBlock {block_id}:")  # 顯示區塊

            block_hashes = []  # 存該區塊所有節點的 hash

            for ip in sorted(all_hashes.keys()):  # 每個節點
                h = all_hashes[ip].get(block_id, "MISSING")  # 取得 hash，不存在則 MISSING
                block_hashes.append(h)  # 加入比對

                if h == "MISSING":  # 缺區塊
                    print(f"Node {ip}: MISSING")
                else:
                    print(f"Node {ip}: {h[:16]}...")  # 顯示 hash 前 16 碼

            if len(set(block_hashes)) == 1:  # 如果完全一樣
                print("結果：一致")
            else:
                print("結果：衝突")

    def check_chain_self_heal(self):
        """checkchain：自癒修復缺失或被竄改的區塊"""

        all_blocks = {}  # 存所有節點的區塊完整資料

        all_blocks[self.my_ip] = self.get_all_block_data()  # 先放自己的區塊資料

        for peer_ip, peer_port in self.peers:  # 向其他節點要求完整區塊
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:  # 建立 TCP socket
                    s.settimeout(1)  # 設定 timeout
                    s.connect((peer_ip, peer_port))  # 連線 peer
                    s.sendall("REQ_ALL_BLOCKS".encode())  # 要求所有區塊完整內容

                    data = s.recv(65535).decode()  # 接收回覆

                    if data.startswith("ALL_BLOCKS"):  # 如果格式正確
                        parts = data.split(" ", 2)  # 拆成 ALL_BLOCKS、IP、內容
                        ip = parts[1]  # 節點 IP
                        body = parts[2] if len(parts) > 2 else ""  # 區塊內容

                        peer_blocks = {}  # 存這個 peer 的區塊資料

                        if body:  # 如果有資料
                            items = body.split("##")  # 拆每個區塊

                            for item in items:
                                if not item:  # 空字串跳過
                                    continue

                                block_id, h, content = item.split("::", 2)  # 拆區塊 ID、hash、內容

                                peer_blocks[int(block_id)] = {  # 存入 peer_blocks
                                    "hash": h,
                                    "content": content.replace("\\n", "\n")  # 還原換行
                                }

                        all_blocks[ip] = peer_blocks  # 存該 peer 的所有區塊

            except:
                print(f"⚠️ 無法連線到節點 {peer_ip}")  # 連線失敗

        all_block_ids = set()  # 存所有出現過的區塊 ID

        for blocks in all_blocks.values():  # 掃所有節點
            all_block_ids.update(blocks.keys())  # 收集區塊 ID

        print("\n--- checkchain 自癒檢查 ---")  # 標題

        for block_id in sorted(all_block_ids):  # 逐一檢查每個區塊
            print(f"\n檢查 Block {block_id}...")  # 顯示目前檢查哪個區塊

            versions = {}  # 存不同版本：{hash: {"count": 次數, "content": 內容}}

            for ip, blocks in all_blocks.items():  # 掃每個節點
                if block_id not in blocks:  # 如果該節點沒有這個區塊
                    print(f"Node {ip}: MISSING")
                    continue

                h = blocks[block_id]["hash"]  # 該區塊 hash
                content = blocks[block_id]["content"]  # 該區塊內容

                print(f"Node {ip}: {h[:16]}...")  # 顯示 hash

                if h not in versions:  # 如果這個版本第一次出現
                    versions[h] = {
                        "count": 0,
                        "content": content
                    }

                versions[h]["count"] += 1  # 此版本數量 +1

            if not versions:  # 如果沒有任何節點有此區塊
                print("結果：沒有任何節點有此區塊，無法修復")
                continue

            correct_hash = max(  # 找出最多節點擁有的版本
                versions.keys(),
                key=lambda h: versions[h]["count"]
            )

            correct_content = versions[correct_hash]["content"]  # 多數版本內容
            correct_count = versions[correct_hash]["count"]  # 多數版本出現次數

            local_block = all_blocks[self.my_ip].get(block_id)  # 本機該區塊

            if local_block is None or local_block["hash"] != correct_hash:  # 如果本機缺失或錯誤
                with open(f"{STORAGE_DIR}/{block_id}.txt", 'w') as f:  # 覆蓋成本機正確版本
                    f.write(correct_content)

                print(f"🔧 Block {block_id} 已自動修復成多數版本")  # 顯示修復

            else:
                print(f"✅ Block {block_id} 正常")  # 本機正常

            if correct_count < 2:  # 如果沒有至少兩個節點一致
                print("⚠️ 注意：此區塊沒有達到 2 個節點以上共識，修復可信度較低")

    def menu(self):
        """使用者輸入指令選單"""

        while True:
            print(f"\n[{self.my_ip}] tx, mine, checkmoney, checklog, checkchain, checkall")
            cmd = input("> ").strip().split()  # 讀取指令

            if not cmd:  # 沒輸入就重來
                continue

            if cmd[0] == "tx":  # 發送交易
                self.tx(cmd[1], cmd[2], float(cmd[3]), float(cmd[4]))

            elif cmd[0] == "mine":  # 挖礦
                self.mine()

            elif cmd[0] == "checkmoney":  # 查餘額
                print(f"💰 {cmd[1]} 餘額: {self.get_balance(cmd[1])}")

            elif cmd[0] == "checklog":  # 查看本地所有區塊內容
                last_id = self.get_last_block_id()  # 最新區塊編號

                if last_id == 0:  # 沒有區塊
                    print("📭 目前尚無區塊紀錄。")
                else:
                    for i in range(1, last_id + 1):  # 印出每個區塊
                        path = f"{STORAGE_DIR}/{i}.txt"

                        if os.path.exists(path):  # 如果區塊存在
                            with open(path, 'r') as f:
                                print(f"\n--- Block {i} ---\n{f.read().strip()}")
                        else:
                            print(f"\n⚠️ 區塊 {i} 檔案缺失，請執行 checkchain 修復。")

            elif cmd[0] == "checkchain":  # 自癒修復區塊
                self.check_chain_self_heal()

            elif cmd[0] == "checkall":  # 比對三個 Docker 所有區塊
                self.check_all_blocks()

    def start(self):
        """啟動節點"""

        threading.Thread(target=self.listen, daemon=True).start()  # 開背景執行緒監聽網路
        self.menu()  # 進入選單


if __name__ == "__main__":  # 主程式入口

    if len(sys.argv) < 2:  # 如果沒有輸入 IP
        print("Usage: python3 p2p_ledger.py <MY_IP>")
        sys.exit(1)

    my_ip = sys.argv[1]  # 從命令列取得自己的 IP

    all_nodes = [  # 三個 Docker 節點
        ('172.18.0.2', 8001),
        ('172.18.0.3', 8001),
        ('172.18.0.4', 8001)
    ]

    peers = [n for n in all_nodes if n[0] != my_ip]  # 排除自己

    P2PLedger(my_ip, peers).start()  # 啟動節點

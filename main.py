from fastapi import FastAPI
import time
import asyncio

app = FastAPI()

class IdWorker:
    def __init__(self, worker_id: int, datacenter_id: int):
        # 工作节点ID和数据中心ID的位数
        self.worker_id_bits = 5
        self.datacenter_id_bits = 5
        # 计算最大可用的工作节点ID和数据中心ID
        self.max_worker_id = -1 ^ (-1 << self.worker_id_bits)
        self.max_datacenter_id = -1 ^ (-1 << self.datacenter_id_bits)

        # 检查worker_id和datacenter_id的值是否在有效的范围内
        if not (0 <= worker_id <= self.max_worker_id):
            raise ValueError(f"worker_id must be between 0 and {self.max_worker_id}")
        if not (0 <= datacenter_id <= self.max_datacenter_id):
            raise ValueError(f"datacenter_id must be between 0 and {self.max_datacenter_id}")

        # 工作节点ID，用于标识在哪个节点上生成的ID
        self.worker_id = worker_id
        # 数据中心ID，用于标识在哪个数据中心生成的ID
        self.datacenter_id = datacenter_id
        # 序列号，用于在同一毫秒内生成不同的ID
        self.sequence = 0
        # 初始时间戳，这里设置为Twitter首次发布雪花算法的时间（2010-11-04）
        self.twepoch = 1288834974657
        # 序列号的位数
        self.sequence_bits = 12
        # 计算工作节点ID、数据中心ID和时间戳需要左移的位数
        self.worker_id_shift = self.sequence_bits
        self.datacenter_id_shift = self.sequence_bits + self.worker_id_bits
        self.timestamp_left_shift = self.sequence_bits + self.worker_id_bits + self.datacenter_id_bits
        # 序列号的掩码，用于确保序列号不会超出最大值
        self.sequence_mask = -1 ^ (-1 << self.sequence_bits)
        # 最后一次生成ID的时间戳
        self.last_timestamp = -1
        # 初始化锁，用于控制并发访问
        self.lock = asyncio.Lock()

    async def _til_next_millis(self, last_timestamp):
        # 等待到下一个毫秒，这是为了防止在同一毫秒内序列号用完的情况
        timestamp = self._time_gen()
        while timestamp <= last_timestamp:
            await asyncio.sleep(0)
            timestamp = self._time_gen()
        return timestamp

    def _time_gen(self):
        # 获取当前时间戳，单位是毫秒
        return int(time.time() * 1000)

    async def get_id(self):
        # 生成ID
        async with self.lock:
            timestamp = self._time_gen()
            if self.last_timestamp == timestamp:
                # 如果当前时间戳等于最后一次生成ID的时间戳，那么在同一毫秒内生成ID
                self.sequence = (self.sequence + 1) & self.sequence_mask
                if self.sequence == 0:
                    # 序列号用完，等待到下一个毫秒
                    timestamp = await self._til_next_millis(self.last_timestamp)
            else:
                # 如果当前时间戳不等于最后一次生成ID的时间戳，那么直接生成ID
                self.sequence = 0
            if timestamp < self.last_timestamp:
                # 如果当前时间戳小于最后一次生成ID的时间戳，那么表示时钟回拨，抛出异常
                raise Exception(f"Clock moved backwards. Refusing to generate id for {self.last_timestamp - timestamp} milliseconds")
            self.last_timestamp = timestamp
            # 返回生成的ID，由时间戳、数据中心ID、工作节点ID和序列号组成
            return ((timestamp - self.twepoch) << self.timestamp_left_shift) | (self.datacenter_id << self.datacenter_id_shift) | (self.worker_id << self.worker_id_shift) | self.sequence


# 创建IdWorker实例，可以根据需要设置工作节点ID和数据中心ID
id_worker = IdWorker(worker_id=0, datacenter_id=0)

@app.get("/")
async def get_id():
    # 处理GET请求，返回生成的ID
    return {"id": await id_worker.get_id()}


@app.get("/backtest")
async def backtest():
    # 保存当前时间
    now = time.time()

    # 生成 ID
    id1 = await id_worker.get_id()

    # 将系统时间设置为之前的时间
    time.time = lambda: now - 60

    # 尝试生成 ID
    try:
        id2 = await id_worker.get_id()
    except Exception as e:
        result = f"Caught exception: {e}"
    else:
        result = f"Generated ID: {id2}"

    # 恢复系统时间
    time.time = lambda: now

    return {"result": result}
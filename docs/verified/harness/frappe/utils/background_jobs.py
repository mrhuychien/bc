"""frappe.utils.background_jobs giả: hàng đợi RQ dựng tay cho bộ thử (không Redis)."""
FAKE_QUEUES: list = []        # [FakeQueue(name, count)]
FAKE_ENQUEUED_IDS: set = set()  # job_id đang chờ / đang chạy
FAKE_REDIS_DOWN = False       # True: get_queues ném lỗi như khi Redis không nối được


class FakeQueue:
	def __init__(self, name, count):
		self.name, self.count = name, count


def get_queues(connection=None):
	if FAKE_REDIS_DOWN:
		raise ConnectionError("redis_queue không nối được")
	return list(FAKE_QUEUES)


def is_job_enqueued(job_id):
	return job_id in FAKE_ENQUEUED_IDS

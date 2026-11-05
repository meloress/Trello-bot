from db.models.order_topic import OrderTopic
from db.repositories.base import BaseRepository


class OrderTopicRepository(BaseRepository[OrderTopic]):
    model = OrderTopic

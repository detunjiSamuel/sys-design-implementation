from channels.generic.websocket import AsyncJsonWebsocketConsumer

ALERTS_GROUP = "price_alerts"


class AlertConsumer(AsyncJsonWebsocketConsumer):
    """
    Clients connect here to receive real-time price-alert notifications.
    All connected clients share a single channel group; every triggered
    alert is broadcast to all of them.
    """

    async def connect(self):
        await self.channel_layer.group_add(ALERTS_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(ALERTS_GROUP, self.channel_name)

    async def alert_triggered(self, event):
        await self.send_json(event["data"])

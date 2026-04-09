from channels.generic.websocket import AsyncJsonWebsocketConsumer


class PriceFeedConsumer(AsyncJsonWebsocketConsumer):
    """Pushes live prices to browser clients subscribed to an asset."""

    async def connect(self):
        self.asset = self.scope["url_route"]["kwargs"]["asset"].upper()
        self.group_name = f"prices_{self.asset}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def price_update(self, event):
        await self.send_json(event["data"])

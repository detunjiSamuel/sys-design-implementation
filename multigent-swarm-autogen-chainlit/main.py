
import chainlit as cl


@cl.on_message
async def on_message(message: cl.Message):

 print(cl.chat_context.to_openai())

 res = f"Echo: {message.content}"
 await cl.Message(res).send()

from requests import get
from diskcache import Cache
from threading import Thread
from base64 import b64encode
from contextlib import suppress
from colorama import Fore, Style
from time import sleep as delay, time
from inspect import signature as inspect_signature
from typing import BinaryIO, Callable, List, Union

from .entities import *
from .utilities.commands import Command, Commands

class Context():
    """
    `Context` - This handles the event context.

    `**Parameters**``
    - `message` - The message which triggered the event.
    - `session` - The session we will use to send requests.

    """
    def __init__(self, message: Message, session, intents: bool):
        self.intents:   bool = intents
        self.message:   Message = message
        self.userId:    str = session.userId
        self.request    = session

    @property
    def author(self) -> MessageAuthor:
        """The author of the message."""
        with suppress(AttributeError):
            return self.message.author

    @property
    def communityId(self) -> str:
        """Sets the url to community/global."""
        return {True: "g", False: f"x{self.message.comId}"}[self.message.comId == 0]

    @property
    def comId(self) -> str:
        """The community ID."""
        return self.message.comId

    @property
    def chatId(self) -> str:
        """The chat ID."""
        return self.message.chatId

    @property
    def api(self) -> str:
        """The API url."""
        return "http://service.aminoapps.com/api/v1"

    @property
    def __message_endpoint__(self) -> str:
        """The message endpoint."""
        return f"/{self.communityId}/s/chat/thread/{self.message.chatId}/message"

    def _run(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
                if isinstance(args[0], Context):
                    return func(*args, **kwargs)
                else:
                    raise MustRunInContext
        return wrapper

    def __purge__(self, data: dict) -> dict:
        return {k: v for k, v in data.items() if v is not None}

    def __prepare_message__(self, **kwargs) -> dict:
        return self.__purge__(self.__parse_kwargs__(**kwargs))    
    
    def __read_image__(self, image: Union[str, BinaryIO]) -> BinaryIO:
        try:
            return get(image).content if image.startswith("http") else open(image, "rb").read()
        except InvalidImage as e:
            raise InvalidImage from e

    def __parse_kwargs__(self, **kwargs) -> dict:
        return {
            "content": kwargs.get("content"),
            "type": kwargs.get("type"),
            "mediaType": kwargs.get("mediaType"),
            "mediaValue": kwargs.get("mediaValue"),
            "mediaUploadValue": kwargs.get("mediaUploadValue"),
            "stickerId": kwargs.get("stickerId"),
            "attachedObject": kwargs.get("attachedObject"),
            "uid": self.userId
            } 

    def __message__(self, **kwargs) -> dict:
        return PrepareMessage(**kwargs).json()

    def __send_message__(self, **kwargs) -> CMessage:
        return CMessage(self.request.handler(
            method = "POST",
            url = self.__message_endpoint__,
            data = self.__message__(**kwargs)
            ))

    def _delete(self, delete_message: CMessage, delete_after: int = 5) -> ApiResponse:
        """
        `delete` - Deletes a message.
        
        `**Parameters**`
        - `delete_message` - The message to delete.
        - `delete_after` - The time to delay before deleting the message.
        
        """
        delay(delete_after)
        return ApiResponse(self.request.handler(
            method = "DELETE",
            url = f"/{self.communityId}/s/chat/thread/{self.message.chatId}/message/{delete_message.messageId}"
            ))
    
    def wait_for_message(self, message: str, timeout: int = 10) -> Message:
        """
        `wait_for_message` - This waits for a message. 
        
        `**Parameters**`
        - `message` - The message to wait for.
        - `timeout` - The time to wait before timing out.
        
        `**Returns**`
        - `Message` - The message that was sent.
        
        `**Example**`
        ```py
        @bot.on_member_join()
        def on_member_join(ctx: Context):
            if ctx.comId != bot.community.community_id:
                return
                
            TIMEOUT = 15

            ctx.send(content="Welcome to the chat! Please verify yourself by typing `$verify` in the chat.", delete_after=TIMEOUT)

            response = ctx.wait_for_message(message="$verify", timeout=15)

            if response is None:
                ctx.send(content="You took too long to verify yourself. You have been kicked from the chat.", delete_after=TIMEOUT)
                return bot.community.kick(userId=ctx.author.userId, chatId=ctx.chatId, allowRejoin=True, comId=ctx.comId)

            else:
                ctx.send(content="You have been verified!", delete_after=TIMEOUT)
        ```
        """
        if not self.intents:
            raise IntentsNotEnabled

        start = time()
        cache = Cache("cache")
        
        while time() - start < timeout:
            cached_message = cache.get(f"{self.message.chatId}_{self.message.author.userId}")

            if cached_message == message:
                cache.clear(f"{self.message.chatId}_{self.message.author.userId}")
                return self.message

            if all([cached_message is not None, cached_message != message]):
                cache.clear(f"{self.message.chatId}_{self.message.author.userId}")
                return None

        cache.clear(f"{self.message.chatId}_{self.message.author.userId}")
        return None

    @_run
    def send(self, content: str, delete_after: int= None, mentioned: Union[str, List[str]]= None) -> CMessage:
        """
        `send` - This sends a message.

        `**Parameters**``
        - `content` - The message you want to send.
        - `delete_after` - The time in seconds before the message is deleted. [Optional]
        - `mentioned` - The user(s) you want to mention. [Optional]

        `**Returns**`` - CMessage object.

        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.send(content="Hello World!", delete_after=None)
        ```
        """
        message: CMessage = self.__send_message__(
            content=content,
            extensions = {
            "mentionedArray": [{"uid": user} for user in mentioned] if mentioned else None
            })

        Thread(target=self._delete, args=(message, delete_after)).start() if delete_after else None

        return message

    @_run
    def reply(self, content: str, delete_after: int= None, mentioned: Union[str, List[str]]= None) -> CMessage:
        """
        `reply` - This replies to the message.

        `**Parameters**``
        - `content` - The message you want to send.
        - `delete_after` - The time in seconds before the message is deleted. [Optional]
        - `mentioned` - The user(s) you want to mention. [Optional]

        `**Returns**`` - CMessage object.

        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.reply(content = "Hello World!", delete_after = None)
        ```
        """
        message: CMessage = self.__send_message__(
            content=content,
            replyMessageId=self.message.messageId,
            extensions = {
            "mentionedArray": [{"uid": user} for user in mentioned] if mentioned else None
            })
        
        Thread(target=self._delete, args=(message, delete_after)).start() if delete_after else None
        
        return message

    def prepare_mentions(self, mentioned: list) -> list:
        """
        `prepare_mentions` - This prepares the mentions for the message.
        
        `**Parameters**``
        - `mentioned` - `ctx.message.mentioned_user_names`.
        
        `**Returns**``
        - `list` - The list of mentions to use as your `message`

        `**Example**``
        ```py
        @bot.command("mention")
        def mention(ctx: Context):
            mentioned_users = ctx.message.mentioned_user_names
            if not mentioned_users:
                return ctx.reply("You didn't mention anyone!")

            mentioned = ctx.prepare_mentions(mentioned_users)
            return ctx.reply(
                "Mentioned: " + ", ".join(mentioned), mentioned=list(mentioned_users)
            )
        """
        return [f"\u200e\u200f@{username}\u202c\u202d" for username in mentioned]

    @_run
    def send_link_snippet(self, image: str, message: str = "[c]", link: str = "ndc://user-me", mentioned: list = None) -> CMessage:
        """
        `send_link_snippet` - This sends a link snippet.

        `**Parameters**``
        - `image` - The image you want to send. Recommended size: 807x216
        - `message` - The message you want to send.
        - `link` - The link you want to send. [Optional]

        `**Returns**`` - CMessage object.

        `**Example**``
        ```py
        @bot.command("linksnippet")
        def linksnippet(ctx: Context):
            return ctx.send_link_snippet(
                image = "https://i.imgur.com/8ZQZ9Zm.png",
                message = "Hello World!",
                link = "https://www.google.com"
            )
        ```
        """
        if mentioned is None: mentioned = []

        message: CMessage = self.__send_message__(
            content=message,
            extensions = {
                "linkSnippetList": [{
                "mediaType": 100,
                "mediaUploadValue": self.encode_media(
                    self.__handle_media__(media=image, content_type="image/jpg", media_value=False)
                ),
                "mediaUploadValueContentType": "image/png",
                "link": link
                }],
            "mentionedArray": [{"uid": user} for user in mentioned] if mentioned else None
            })

        return message
    
    @_run
    def send_embed(
        self,
        message: str,
        title: str,
        content: str,
        image: str,
        link: str = "ndc://user-me",
        mentioned: Union[str, List[str]]= None
        ) -> CMessage:
        """
        `send_embed` - This sends an embed.

        `**Parameters**``
        - `message` - The message you want to send.
        - `title` - The title of the embed.
        - `content` - The content of the embed.
        - `image` - The image you want to send. Recommended size: 807x216
        - `link` - The link you want to send. [Optional]

        `**Returns**`` - CMessage object.

        `**Example**``
        ```py
        @bot.command("embed")
        def embed(ctx: Context):
            return ctx.send_embed(
                message = "[c]",
                title = "Hello World!",
                content = "This is an embed.",
                image = "https://i.imgur.com/8ZQZ9Zm.png",
                link = "https://www.google.com"
            )
        ```
        """
        message: CMessage = self.__send_message__(
            content=message,
            attachedObject = {
                "title": title,
                "content": content,
                "mediaList": [[100, self.__handle_media__(media=image, media_value=True), None]],
                "link": link
                },
            extensions = {
                "mentionedArray": [{"uid": user} for user in mentioned] if mentioned else None
            })
        
        return message

    def __handle_media__(self, media: str, content_type: str = "image/jpg", media_value: bool = False) -> str:
        response = None
        
        try:
            if media.startswith("http"):
                response = get(media)
                response.raise_for_status()
                media = response.content
            else:
                media = open(media, "rb").read()
        except Exception as e:
            raise InvalidImage from e
        
        if content_type == "audio/aac":
            return self.encode_media(media)

        if media_value:
            return self.upload_media(media=media, content_type=content_type)

        if response and not response.headers.get("content-type").startswith("image"):
            raise InvalidImage

        return media
    

    def encode_media(self, file: bytes) -> str:
        return b64encode(file).decode()

    def upload_media(self, media: Union[str, BinaryIO], content_type: str = "image/jpg") -> str:
        return ApiResponse(self.request.handler(
            method = "POST",
            url = "/g/s/media/upload",
            data = media,
            content_type = content_type
            )).mediaValue
    
    @_run
    def send_sticker(self, sticker_id: str) -> CMessage:
        """
        `send_sticker` - This sends a sticker.

        `**Parameters**``
        - `sticker_id` - The sticker ID you want to send.

        `**Returns**`` - CMessage object.

        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.send_sticker(sticker_id="sticker_id")
        ```
        """
        sticker_id = sticker_id.replace("ndcsticker://", "") if sticker_id.startswith("ndcsticker://") else sticker_id
        message: CMessage = self.__send_message__(
            type=3,
            stickerId=sticker_id,
            mediaValue=f"ndcsticker://{sticker_id}"
            )
        
        return message

    @_run
    def send_image(self, image: str) -> CMessage:
        """
        `send_image` - This sends an image.

        `**Parameters**``
        - `image` - The image link or file you want to send.

        `**Returns**`` - CMessage object.

        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.send_image(image="https://i.imgur.com/image.jpg")
        ```
        """
        message: CMessage = self.__send_message__(
            mediaType=100,
            mediaUploadValue=self.encode_media(
                self.__handle_media__(
                    media=image,
                    content_type="image/jpg",
                    media_value=False
            )))

        return message
            
    @_run
    def send_gif(self, gif: str) -> CMessage:
        """
        `send_gif` - This sends a gif.

        `**Parameters**``
        - `gif` - The gif link or file you want to send.

        `**Returns**`` - CMessage object.

        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.send_gif(gif="https://i.imgur.com/image.gif")
        ```
        """
        message: CMessage = self.__send_message__(
            mediaType=100,
            mediaUploadValueContentType="image/gif",
            mediaUploadValue=self.encode_media(
                self.__handle_media__(
                    media=gif,
                    content_type="image/gif",
                    media_value=False
            )))
        
        return message

    @_run
    def send_audio(self, audio: str) -> CMessage:
        """
        `send_audio` - This sends an audio file.
        
        `**Parameters**``
        - `audio` - The audio link or file you want to send.
        
        `**Returns**`` - CMessage object.
        
        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.send_audio(audio="output.mp3")
        ```
        """
        message: CMessage = self.__send_message__(
            type=2,
            mediaType=110,
            mediaUploadValue=self.__handle_media__(
                    media=audio,
                    content_type="audio/aac",
                    media_value=False
            ))
        
        return message

    @_run
    def join_chat(self, chatId: str=None) -> ApiResponse:
        """
        `join_chat` - This joins a chat.

        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.join_chat(chatId="0000-0000-0000-0000")
        ```
        """
        return ApiResponse(self.request.handler(
            method="POST",
            url=f"/{self.communityId}/s/chat/thread/{chatId or self.chatId}/member/{self.userId}"
            ))

    @_run
    def leave_chat(self, chatId: str=None) -> ApiResponse:
        """
        `leave_chat` - This leaves a chat.

        `**Example**``
        ```py
        @bot.on_text_message()
        def on_text_message(ctx: Context):
            ctx.leave_chat(chatId="0000-0000-0000-0000")
        ```
        """
        return ApiResponse(self.request.handler(
            method="DELETE",
            url=f"/{self.communityId}/s/chat/thread/{chatId or self.chatId}/member/{self.userId}"
            ))
    
class EventHandler: #NEW.
    #OLD: class EventHandler(Context):
    """
    `EventHandler` - AKA where all the events are handled.

    `**Parameters**``
    - `session` - The session we are using.

    """
    def __init__(self):
        self.command_prefix:    str = self.command_prefix
        self._events:           dict = {}
        self._wait_for:         Cache = Cache("cache")
        self._commands:         Commands = Commands()
        self.context:           Context = Context


    def start_task(self, func):
        """`start_task` - This starts a task."""
        Thread(target=func).start()


    def _handle_task(self, func, interval):
        """
        `_handle_task` - This handles the task.
        
        `**Parameters**``
        - `func` - The function.
        - `interval` - The interval in seconds.
        
        `**Returns**`` - None
        """
        while True:
            if len(inspect_signature(func).parameters) == 0:
                func()
            else: func(self.community)
            delay(interval)


    def task(self, interval: int = 10):
        """
        `task` - This creates a task.

        `**Parameters**``
        - `interval` - The interval in seconds.

        `**Example**``
        ```py
        # This will print "Hello World!" every 10 seconds.
        @bot.task(interval=10)
        def task():
            print("Hello World!")

        # This will send a message to a chat every 120 seconds.
        @bot.task(interval=120)
        def task(community: Community):
            community.send_message(chatId=0000-0000-0000-0000, content="Hello World!")
        ```
        """

        def decorator(func):
            def wrapper():
                self._handle_task(func, interval)
            self.start_task(wrapper)
        return decorator


    def _set_parameters(self, context: Context, func: Callable, message: str = None) -> list:
        try:
            message = message if isinstance(message, str) else context.message.content
        except AttributeError:
            message = None

        try:
            username = context.author.username
        except AttributeError:
            username = None

        try:
            userId = context.author.userId
        except AttributeError:
            userId = None

        potential_parameters = {
            "ctx": context,
            "member": Member(context.author.json()),
            "message": message,
            "username": username,
            "userId": userId
        }

        return [
            potential_parameters.get(parameter)
            for parameter in inspect_signature(func).parameters
        ]


    def emit(self, name: str, *args) -> None:
        """`emit` is a function that emits an event."""
        self._events[name](*args) if name in self._events else None


    def command(
        self,
        name: str=None,
        description: str=None,
        usage: str=None,
        aliases: list=[],
        cooldown: int=0,
        **kwargs
    ) -> Callable:
        """
        `command` - This creates a command.
        
        `**Command Parameters**``
        - `command_name` - The name of the command.
        - `command_description` - The description of the command.
        - `aliases` - The other names the command can be called by.
        - `cooldown` - The cooldown of the command in seconds.

        `**Function Parameters**``
        - `ctx` - The context of the command.
        - `member` - The Member(member) who called the command.
        - `message` - The message that called the command.
        - `username` - The username of the person who called the command.
        - `userId` - The userId of the person who called the command.

        Do I need a `command_description`?
            - No, you don't need a command description however it is recommended.
            - If you don't supply a command description the command will not show up in the help command.

        What are `aliases`?
            - The command can be called by the command name, aliases, or both.

        Is `cooldown` required?
            - No, you don't need a cooldown however it is recommended to avoid spam.

        What is the difference between `message` and `ctx.message.content`?
            - `ctx.message.content` contains the entire message.        
            - `message` contains the message without the command prefix.

        Do I need to supply all the parameters?
            - No, you only need to supply the parameters you want to use however `ctx` is required.
        
        `**Example**``
        ```py
        @bot.command(command_name="ping") # Command parameters.
        def ping(ctx: Context, message: str, username: str, userId: str): # Function parameters.
            print(f"{username}({userId}): {message}") # OUTPUT: "JohnDoe(0000-0000-0000-0000): !ping"
            return ctx.send(content="Pong!")

        @bot.command(command_name="ping", aliases=["alive", "test"]) # Command parameters.
        def ping(ctx: Context): # Function parameters.
            # This command can be called by "ping", "alive", and "test".
            return ctx.send(content="Pong!")

        @bot.command(command_name="ping", cooldown=5) # Command parameters.
        def ping(ctx: Context): # Function parameters.
            # This command can only be called every 5 seconds.
            return ctx.send(content="Pong!")

        @bot.command(command_name="say", command_description="This is a command that says something.") # Command parameters.
        def say(ctx: Context, message: str, username: str, userId: str): # Function parameters.
            bot.community.delete_message(chatId=ctx.chatId, messageId=ctx.message.chatId, comId=ctx.comId)
            return ctx.send(content=message)
        ```
        """
        
        if "command_name" in kwargs:
            self._is_deprecated("command_name", "name")
            name = kwargs["command_name"]

        elif name is None:
            raise ValueError("Please supply a name for the command. Example: @bot.command(name='ping')")

        if "command_description" in kwargs:
            self._is_deprecated("command_description", "description")
            description = kwargs["command_description"]

        def decorator(func: Callable) -> Callable:
            self._commands.add_command(
                Command(
                    func=func,
                    name=name,
                    description=description,
                    usage=usage,
                    aliases=aliases,
                    cooldown=cooldown
                ))
            return func
        return decorator


    def _is_deprecated(self, parameter: str, new_parameter: str):
        print(f"{Style.BRIGHT}{Fore.RED}WARNING:{Style.RESET_ALL} '{parameter}' is deprecated. Please use '{new_parameter}' instead.")


    def command_exists(self, command_name: str) -> bool:
        return any([
            command_name in self._commands.__command_names__(),
            command_name in self._commands.__command_aliases__()
            ])


    def fetch_command(self, command_name: str) -> Command:
        return self._commands.fetch_command(command_name)

    def _handle_command(self, data: Message, context: Context):
        """Handles commands."""
        command_name = data.content[len(self.command_prefix):].split(" ")[0]

        if (not self.command_exists(command_name) or
                self.command_prefix != data.content[:len(self.command_prefix)]):

            if (command_name == "help" and
                    data.content == f"{self.command_prefix}help"):
                return context.reply(self._commands.__help__())

            elif any(
                event in self._events
                for event in {"text_message", "_console_text_message"}
            ):
                for event in {"text_message", "_console_text_message"}:
                    self._handle_all_events(event=event, data=data, context=context)
                return None

            else:
                return None

        if data.content[:len(self.command_prefix)] != self.command_prefix:
            return None

        message = data.content[len(self.command_prefix) + len(command_name) + 1:]
        command_name = dict(self._commands.__command_aliases__().copy()).get(command_name, command_name)

        response = self._check_cooldown(command_name, data, context)

        if response != 403:
            func = self._commands.fetch_command(command_name).func
            return func(*self._set_parameters(context=context, func=func, message=message))

        return None

        
    def _check_cooldown(self, command_name: str, data: Message, context: Context) -> None:
        """`_check_cooldown` is a function that checks if a command is on cooldown."""
        if self._commands.fetch_command(command_name).cooldown > 0:
            if self._commands.fetch_cooldown(command_name, data.author.userId) > time():

                context.reply(
                    content=f"You are on cooldown for {int(self._commands.fetch_cooldown(command_name, data.author.userId) - time())} seconds."
                    )
                return 403
            
            self._commands.set_cooldown(
                command_name=command_name,
                cooldown=self._commands.fetch_command(command_name).cooldown,
                userId=data.author.userId
                )

        return 200


    def on_error(self):
        def decorator(func: Callable) -> Callable:
            self._events["error"] = func
            return func
        return decorator


    def on_ready(self):
        def decorator(func: Callable) -> Callable:
            self._events["ready"] = func
            return func
        return decorator


    def on_text_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["text_message"] = func
            return func
        return decorator
    
    def _console_on_text_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["_console_text_message"] = func
            return func
        return decorator


    def _add_cache(self, chatId: str, userId: str, content: str):
        if self._wait_for.get(f"{chatId}_{userId}") is not None:
            self._wait_for.clear(f"{chatId}_{userId}")

        self._wait_for.add(
            key=f"{chatId}_{userId}",
            value=content,
            expire=90
            )


    def on_image_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["image_message"] = func
            return func
        return decorator


    def on_youtube_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["youtube_message"] = func
            return func
        return decorator


    def on_strike_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["strike_message"] = func
            return func
        return decorator


    def on_voice_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["voice_message"] = func
            return func
        return decorator


    def on_sticker_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["sticker_message"] = func
            return func
        return decorator


    def on_vc_not_answered(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_not_answered"] = func
            return func
        return decorator


    def on_vc_not_cancelled(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_not_cancelled"] = func
            return func
        return decorator


    def on_vc_not_declined(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_not_declined"] = func
            return func
        return decorator


    def on_video_chat_not_answered(self):
        def decorator(func: Callable) -> Callable:
            self._events["video_chat_not_answered"] = func
            return func
        return decorator


    def on_video_chat_not_cancelled(self):
        def decorator(func: Callable) -> Callable:
            self._events["video_chat_not_cancelled"] = func
            return func
        return decorator


    def on_video_chat_not_declined(self):
        def decorator(func: Callable) -> Callable:
            self._events["video_chat_not_declined"] = func
            return func
        return decorator


    def on_avatar_chat_not_answered(self):
        def decorator(func: Callable) -> Callable:
            self._events["avatar_chat_not_answered"] = func
            return func
        return decorator


    def on_avatar_chat_not_cancelled(self):
        def decorator(func: Callable) -> Callable:
            self._events["avatar_chat_not_cancelled"] = func
            return func
        return decorator


    def on_avatar_chat_not_declined(self):
        def decorator(func: Callable) -> Callable:
            self._events["avatar_chat_not_declined"] = func
            return func
        return decorator


    def on_delete_message(self):
        def decorator(func: Callable) -> Callable:
            def wrapper(ctx: Context):
                func(*self._set_parameters(ctx, func))
            self._events["delete_message"] = wrapper
            return func
        return decorator


    def on_member_join(self):
        def decorator(func: Callable) -> Callable:
            self._events["member_join"] = func
            return func
        return decorator


    def on_member_leave(self):
        def decorator(func: Callable) -> Callable:
            self._events["member_leave"] = func
            return func
        return decorator


    def on_chat_invite(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_invite"] = func
            return func
        return decorator


    def on_chat_background_changed(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_background_changed"] = func
            return func
        return decorator


    def on_chat_title_changed(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_title_changed"] = func
            return func
        return decorator


    def on_chat_icon_changed(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_icon_changed"] = func
            return func
        return decorator


    def on_vc_start(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_start"] = func
            return func
        return decorator


    def on_video_chat_start(self):
        def decorator(func: Callable) -> Callable:
            self._events["video_chat_start"] = func
            return func
        return decorator


    def on_avatar_chat_start(self):
        def decorator(func: Callable) -> Callable:
            self._events["avatar_chat_start"] = func
            return func
        return decorator


    def on_vc_end(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_end"] = func
            return func
        return decorator


    def on_video_chat_end(self):
        def decorator(func: Callable) -> Callable:
            self._events["video_chat_end"] = func
            return func
        return decorator


    def on_avatar_chat_end(self):
        def decorator(func: Callable) -> Callable:
            self._events["avatar_chat_end"] = func
            return func
        return decorator


    def on_chat_content_changed(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_content_changed"] = func
            return func
        return decorator


    def on_screen_room_start(self):
        def decorator(func: Callable) -> Callable:
            self._events["screen_room_start"] = func
            return func
        return decorator


    def on_screen_room_end(self):
        def decorator(func: Callable) -> Callable:
            self._events["screen_room_end"] = func
            return func
        return decorator


    def on_chat_host_transfered(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_host_transfered"] = func
            return func
        return decorator


    def on_text_message_force_removed(self):
        def decorator(func: Callable) -> Callable:
            self._events["text_message_force_removed"] = func
            return func
        return decorator


    def on_chat_removed_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_removed_message"] = func
            return func
        return decorator


    def on_mod_deleted_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["mod_deleted_message"] = func
            return func
        return decorator


    def on_chat_tip(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_tip"] = func
            return func
        return decorator


    def on_chat_pin_announcement(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_pin_announcement"] = func
            return func
        return decorator


    def on_vc_permission_open_to_everyone(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_permission_open_to_everyone"] = func
            return func
        return decorator


    def on_vc_permission_invited_and_requested(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_permission_invited_and_requested"] = func
            return func
        return decorator


    def on_vc_permission_invite_only(self):
        def decorator(func: Callable) -> Callable:
            self._events["vc_permission_invite_only"] = func
            return func
        return decorator


    def on_chat_view_only_enabled(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_view_only_enabled"] = func
            return func
        return decorator


    def on_chat_view_only_disabled(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_view_only_disabled"] = func
            return func
        return decorator


    def on_chat_unpin_announcement(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_unpin_announcement"] = func
            return func
        return decorator


    def on_chat_tipping_enabled(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_tipping_enabled"] = func
            return func
        return decorator


    def on_chat_tipping_disabled(self):
        def decorator(func: Callable) -> Callable:
            self._events["chat_tipping_disabled"] = func
            return func
        return decorator


    def on_timestamp_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["timestamp_message"] = func
            return func
        return decorator


    def on_welcome_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["welcome_message"] = func
            return func
        return decorator


    def on_share_exurl_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["share_exurl_message"] = func
            return func
        return decorator
    

    def on_invite_message(self):
        def decorator(func: Callable) -> Callable:
            self._events["invite_message"] = func
            return func
        return decorator


    def on_user_online(self):
        def decorator(func: Callable) -> Callable:
            self._events["user_online"] = func
            return func
        return decorator


    def on_member_set_you_host(self):
        """
        `on_member_set_you_host` - This is an event that is called when you are set as host.

        `**Example**``
        ```py
        from pymino.ext import *
        chatId = "0000-0000-0000-0000"

        @bot.on_member_set_you_host()
        def member_set_you_host(notification: Notification):
            if notification.chatId == chatId:
                print("You are now host")
                bot.community.send_message(chatId=chatId, content="I am now host", comId=notification.comId)
        ```
        """
        def decorator(func: Callable) -> Callable:
            self._events["member_set_you_host"] = func
            return func
        return decorator


    def on_member_set_you_cohost(self):
        """
        `on_member_set_you_cohost` - This is an event that is called when you are set as cohost.
        
        `**Example**``
        ```py
        from pymino.ext import *
        chatId = "0000-0000-0000-0000"
        
        @bot.on_member_set_you_cohost()
        def member_set_you_cohost(notification: Notification):
            if notification.chatId == chatId:
                print("You are now cohost")
                bot.community.send_message(chatId=chatId, content="I am now cohost", comId=notification.comId)
        ```
        """
        def decorator(func: Callable) -> Callable:
            self._events["member_set_you_cohost"] = func
            return func
        return decorator


    def on_member_remove_your_cohost(self):
        """
        `on_member_remove_your_cohost` - This is an event that is called when you are removed as cohost.
        
        `**Example**``
        ```py
        from pymino.ext import *
        chatId = "0000-0000-0000-0000"
        
        @bot.on_member_remove_your_cohost()
        def member_remove_your_cohost(notification: Notification):
            if notification.chatId == chatId:
                print("You are no longer cohost")
                bot.community.send_message(chatId=chatId, content="I am no longer cohost", comId=notification.comId)
        ```
        """
        def decorator(func: Callable) -> Callable:
            self._events["member_remove_your_cohost"] = func
            return func
        return decorator


    def _handle_all_events(self, event: str, data: Message, context: Context) -> None:
        func = self._events[event]
        return func(* self._set_parameters(context, func, data))


    def _handle_event(
        self,
        event: str,
        data: Union[Message, OnlineMembers, Notification, Context]
        ) -> Union[Context, None]:
        """
        `_handle_event` is a function that handles events.
        """
        with suppress(KeyError):

            if event == "text_message":
                context = self.context(data, self.request, self.intents)
                if all([self.intents, not self.command_exists(
                    command_name=data.content[len(self.command_prefix):].split(" ")[0]
                    )]):
                        self._add_cache(data.chatId, data.author.userId, data.content)

                self._handle_command(data=data, context=context)
            
            if event in self._events:
                context = self.context(data, self.request, self.intents)

                if event in {
                    "user_online",
                    "member_set_you_host",
                    "member_set_you_cohost",
                    "member_remove_your_cohost",
                }:
                    return self._events[event](data)

                else:
                    return self._handle_all_events(event=event, data=data, context=context)
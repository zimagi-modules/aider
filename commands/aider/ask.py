from systems.commands.index import Command


class Ask(Command("dev.aider.ask")):

    def exec(self):
        self.info(self.ask_aider(self.query))

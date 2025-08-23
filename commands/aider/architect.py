from systems.commands.index import Command


class Architect(Command("dev.aider.architect")):

    def exec(self):
        self.info(self.architect_with_aider(self.instruction))

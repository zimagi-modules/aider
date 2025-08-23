from systems.commands.index import Command


class Code(Command("aider.code")):

    def exec(self):
        self.info(self.code_with_aider(self.instruction))

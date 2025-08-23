import copy
import os

from systems.commands.index import CommandMixin
from utility.aider import Aider


class AiderMixin(CommandMixin("aider")):

    def get_aider_session(self, error_if_no_context=True):
        def _get_aider_session(read_files):
            session = Aider(
                os.path.join(self.manager.aider_root, self.directory),
                model=self.model,
                write_files=self.write_files,
                read_files=read_files,
                commit=self.commit,
                repo_map_tokens=self.repo_map_tokens,
            )
            if session.info.remaining_tokens < self.write_tokens:
                if len(read_files[:-1]) > 0:
                    return _get_aider_session(read_files[:-1])
                elif error_if_no_context:
                    self.error("Aider session has no context")
            return session

        return _get_aider_session(copy.deepcopy(self.read_files))

    def ask_aider(self, query, error_if_no_context=True):
        session = self.get_aider_session(error_if_no_context)
        return session.ask(query)

    def architect_with_aider(self, instruction, error_if_no_context=True):
        session = self.get_aider_session(error_if_no_context)
        return session.architect(instruction)

    def code_with_aider(self, instruction, error_if_no_context=True):
        session = self.get_aider_session(error_if_no_context)
        return session.code(instruction)

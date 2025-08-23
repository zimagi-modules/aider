import json
import sys

from contextlib import contextmanager
from io import StringIO
from pathlib import Path

from aider.coders import Coder
from aider.commands import Commands, SwitchCoder
from aider.io import InputOutput
from aider.models import Model
from aider.utils import is_image_file

from .display import capture_output


class AiderFileInfo:

    def __init__(self, name, tokens, token_unit_cost, readonly=False):
        self.name = name
        self.readonly = readonly
        self.tokens = tokens
        self.cost = tokens * token_unit_cost

    def __str__(self):
        return json.dumps(self.export(), indent=2)

    def export(self):
        return {
            "name": self.name,
            "readonly": self.readonly,
            "tokens": self.tokens,
            "cost": self.cost,
        }


class AiderSessionInfo:

    def __init__(self, session):
        self._session = session
        self._coder = session.coder
        self._io = session.io

        self._fence = "`" * 3
        self.load()

    def __str__(self):
        return json.dumps(self.export(), indent=2)

    def export(self):
        return {
            "model": self.model_name,
            "token_unit_cost": self.token_unit_cost,
            "system_tokens": self.system_tokens,
            "system_token_cost": self.system_token_cost,
            "chat_tokens": self.chat_tokens,
            "repo_map_tokens": self.repo_map_tokens,
            "repo_map_token_cost": self.repo_map_token_cost,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "max_tokens": self.max_tokens,
            "remaining_tokens": self.remaining_tokens,
            "files": {file_path: info.export() for file_path, info in self.files.items()},
        }

    @property
    def model_name(self):
        return self._session.model_name

    @property
    def token_unit_cost(self):
        return self._coder.main_model.info.get("input_cost_per_token") or 0

    @property
    def max_tokens(self):
        return self._coder.main_model.info.get("max_input_tokens") or 0

    def reset(self):
        self.system_tokens = 0
        self.system_token_cost = 0
        self.chat_tokens = 0
        self.chat_token_cost = 0
        self.repo_map_tokens = 0
        self.repo_map_token_cost = 0
        self.total_tokens = 0
        self.total_cost = 0
        self.remaining_tokens = 0
        self.files = {}

    def load(self):
        self.reset()
        self._coder.choose_fence()

        messages = self._get_system_messages()
        self.system_tokens = self._coder.main_model.token_count(messages)
        self.system_token_cost = self.system_tokens * self.token_unit_cost

        messages = self._coder.done_messages + self._coder.cur_messages
        if messages:
            self.chat_tokens = self._coder.main_model.token_count(messages)
            self.chat_token_cost = self.chat_tokens * self.token_unit_cost

        files = set(self._coder.get_all_abs_files()) - set(self._coder.abs_fnames)
        if self._coder.repo_map:
            repo_content = self._coder.repo_map.get_repo_map(self._coder.abs_fnames, files)
            if repo_content:
                self.repo_map_tokens = self._coder.main_model.token_count(repo_content)
                self.repo_map_token_cost = self.repo_map_tokens * self.token_unit_cost

        for file_path in self._coder.abs_fnames:
            relative_file_path = self._coder.get_rel_fname(file_path)
            content = self._io.read_text(file_path)

            if is_image_file(relative_file_path):
                tokens = self._coder.main_model.token_count_for_image(file_path)
            else:
                content = f"{relative_file_path}\n{self._fence}\n" + content + f"{self._fence}\n"
                tokens = self._coder.main_model.token_count(content)

            self.files[relative_file_path] = AiderFileInfo(relative_file_path, tokens, self.token_unit_cost, False)

        for file_path in self._coder.abs_read_only_fnames:
            relative_file_path = self._coder.get_rel_fname(file_path)
            content = self._io.read_text(file_path)

            if content is not None and not is_image_file(relative_file_path):
                content = f"{relative_file_path}\n{self._fence}\n" + content + f"{self._fence}\n"
                tokens = self._coder.main_model.token_count(content)

                self.files[relative_file_path] = AiderFileInfo(relative_file_path, tokens, self.token_unit_cost, True)

        self.total_tokens = self.system_tokens + self.chat_tokens + self.repo_map_tokens
        self.total_cost = self.system_token_cost + self.chat_token_cost + self.repo_map_token_cost
        for file_path, info in self.files.items():
            self.total_tokens += info.tokens
            self.total_cost += info.cost

        self.remaining_tokens = self.max_tokens - self.total_tokens
        return self

    def _get_system_messages(self):
        system_message = self._coder.fmt_system_prompt(self._coder.gpt_prompts.main_system)
        system_message += "\n" + self._coder.fmt_system_prompt(self._coder.gpt_prompts.system_reminder)
        return [
            {"role": "system", "content": system_message},
            {"role": "system", "content": self._coder.fmt_system_prompt(self._coder.gpt_prompts.system_reminder)},
        ]


class Aider:

    def __init__(
        self,
        directory,
        write_files=None,
        read_files=None,
        model="openrouter/deepseek/deepseek-r1-0528",
        io=None,
        commit=False,
        repo_map_tokens=1024,
        **kwargs,
    ):
        self.model_name = model
        self._model = Model(self.model_name)
        self._start(directory, write_files, read_files, io=io, commit=commit, repo_map_tokens=repo_map_tokens, **kwargs)

    @property
    def coder(self):
        return self._coder

    @property
    def io(self):
        return self._io

    @property
    def info(self):
        return self._info

    def _start(self, directory, write_files=None, read_files=None, io=None, commit=False, repo_map_tokens=1024, **kwargs):
        self._io = InputOutput(pretty=False, fancy_input=False, yes=True) if io is None else io
        self._coder = Coder.create(
            main_model=self._model,
            io=self._io,
            fnames=[directory],
            map_tokens=repo_map_tokens,
            auto_commits=commit,
            **kwargs,
        )
        self._session = Commands(self._io, self._coder)
        self._info = AiderSessionInfo(self)
        if write_files:
            self.add_write_files(write_files)
        if read_files:
            self.add_read_files(read_files)

    def add_write_files(self, files):
        with capture_output() as output:
            for file in files if isinstance(files, (list, tuple)) else [files]:
                self._session.cmd_add(str(file))
            self._info.load()

    def add_read_files(self, files):
        with capture_output() as output:
            for file in files if isinstance(files, (list, tuple)) else [files]:
                self._session.cmd_read_only(str(file))
            self._info.load()

    def run(self, command, message=""):
        with capture_output() as output:
            try:
                getattr(self._session, f"cmd_{command}")(message)
            except SwitchCoder:
                pass
            return output.getvalue()

    def ask(self, message):
        return self.run("ask", message)

    def architect(self, message):
        return self.run("architect", message)

    def code(self, message):
        return self.run("code", message)

# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

# Standard library imports
import sys
import traceback
import inspect
import fnmatch
import multiprocessing
import os
import threading
from collections import deque

# Third party imports
import sgtk
from sgtk.platform import Application


class TicketsApp(Application):
    '''
    Required Ticket Fields:
        priority (list): List of priority values [1, 2, 3, 4, 5...]
        type (list): List of type values [tool, feature, bug...]
        sg_error (text): Error text (python traceback)
        sg_count (number): Number of times an error has occured
        sg_context (text): Context where the ticket was submitted from
    '''

    def init_app(self):
        # Import Tickets UI
        self.ui = self.import_module("tickets_ui")
        self.engine.register_command(
            "Submit Ticket",
            self.show_tickets_submitter,
        )

        # TicketsIO handles all IO operations for the Tickets App
        self.io = TicketsIO(self)

        # Install Tickets excepthook to deal with unhandled exceptions
        self.excepthook = TicketsExceptHook(self)
        self.excepthook.init()

    def destroy_app(self):
        self.excepthook.destroy()

    def show_tickets_submitter(self, **field_defaults):
        '''Show the Ticket Submission dialog.'''

        field_defaults.setdefault('context', self.context)
        field_defaults.setdefault('assignee', self.get_default_assignee())

        self.ui.tickets_submitter.show(
            self,
            fields=field_defaults,
        )

    def create_exception_ticket(self, typ, value, tb, confirm=False):
        '''Create a new Ticket entity from a python exception.

        Example:
            try:
                x = 10 / 0
            except ZeroDivisionError:
                app.create_exception_ticket(*sys.exc_info())

        Arguments:
            typ: Exception type
            value: Exception instance
            tb: Exception Traceback
            confirm (bool): Show dialog before creating Ticket. (Default False)

        Return:
            Ticket
        '''

        return self.excepthook.create_exception_ticket(typ, value, tb, confirm)

    def create_ticket(
        self,
        fields,
        context=None,
        attachments=None,
        error=None,
        exc_info=None,
    ):
        '''Create a new Ticket entity.

        Arguments:
            fields (dict): Ticket data
            context (Context): Optional Context - defaults to current context
            extra_context (Context):
            attachments (list): Optional files to attach to Ticket
            error (str): Optional error string
            exc_info (typ, value, tb): Optional Exception info

        Return:
            Ticket
        '''

        # Get Ticket Context
        ticket_context = self._context_to_dict(context or self.context)

        # Add traceback details and set error message
        if exc_info:
            tb_details = self.excepthook.get_traceback_details(exc_info[2])
            ticket_context.update(tb_details)
            if not error:
                error = self.excepthook.format_exception(*exc_info)

        # Set project field
        project_id = context.project['id']
        fields.setdefault('project', {'type': 'Project', 'id': project_id})

        # Call events_hook.before_create_ticket allowing users to augment
        # ticket data.
        fields, ticket_context, error = self.execute_hook_method(
            'events_hook',
            'before_create_ticket',
            fields=fields,
            context=ticket_context,
            error=error,
            exc_info=exc_info,
        )

        # Inject context and error message into fields
        fields['sg_context'] = code_block(self._format_context(ticket_context))
        fields['sg_error'] = code_block(error)

        # Create our new ticket
        ticket = self.io.create(fields)

        # Upload our attachments
        if attachments:
            self.io.upload_attachments(ticket['id'], attachments)

        # Create note to force notification to appear in Shotgun Inbox
        self.send_ticket_notification(ticket)

        # Call events_hook.after_create_ticket allowing users to perform
        # an action with the generated ticket data.
        self.execute_hook_method(
            'events_hook',
            'after_create_ticket',
            ticket=ticket,
        )
        return ticket

    def send_ticket_notification(self, ticket):
        '''Create a Note to force Tickets to show up in the Shotgun Inbox.'''

        self.io.send_notification(ticket)

    def get_ticket_url(self, ticket_id):
        url_tmpl = '{base_url}/detail/Ticket/{id}'
        return url_tmpl.format(
            base_url=self.sgtk.shotgun_url,
            id=ticket_id,
        )

    def get_default_assignee(self):
        assignee = self.get_setting('default_assignee')
        if not assignee:
            return

        if assignee['type'] == 'Group':
            return self.shotgun.find_one(
                assignee['type'],
                [['id', 'is', assignee['id']]],
                ['id', 'code']
            )

        if assignee['type'] == 'HumanUser':
            return self.shotgun.find_one(
                assignee['type'],
                [['id', 'is', assignee['id']]],
                ['id', 'name']
            )

    def get_default_project_id(self, context):
        '''Get the project_id for a Ticket.'''

        return context['project']['id']

    def _context_to_dict(self, context):
        '''Convert a Context object to a dict.'''

        return {
            'project': str(context.project),
            'entity': str(context.entity),
            'step': str(context.step),
            'task': str(context.task),
            'user': str(context.user),
            'shotgun_url': str(context.shotgun_url)
        }

    def _format_context(self, context_dict):
        '''Format a context dict to be used in the Ticket "context" field.'''

        shotgun_keys = [
            'project',
            'entity',
            'step',
            'task',
            'user',
            'shotgun_url',
        ]
        data = context_dict.copy()
        lines = ['Shotgun Context']
        for key in shotgun_keys:
            value = data.pop(key, None)
            lines.append('  {}: {}'.format(key, value))
        if data:
            lines.append('Additional Context')
            for key, value in sorted(data.items()):
                lines.append('  {}: {}'.format(key, value))
        return '\n'.join(lines)


class TicketsExceptHook(object):
    '''Creates tickets from unhandled exceptions by installing itself as the
    sys.excepthook.'''

    _is_tickets_excepthook = True

    def __init__(self, app):
        self.app = app
        self._default_excepthook = None
        self._recent_exceptions = []
        try:
            import maya
            self._host = 'maya'
        except ImportError:
            self._host = 'python'

    @property
    def installed(self):
        return self._default_excepthook is not None

    @property
    def enabled(self):
        return self.app.get_setting('excepthook_enabled', True)

    @property
    def includes(self):
        return self.app.get_setting('excepthook_includes', [])

    @property
    def excludes(self):
        return self.app.get_setting('excepthook_excludes', [])

    @property
    def confirm(self):
        return self.app.get_setting('excepthook_confirm', True)

    def init(self):
        '''Install the TicketsExceptHook.'''

        if self.enabled:
            self.app.logger.info('Init excepthook for %s...' % self._host)
            method = getattr(self, '_init_' + self._host)
            return method()
        else:
            self.app.logger.info('Skipping excepthook - disabled in settings.')

    def _init_python(self):
        '''Default python implementation using sys.excepthook.'''

        # Do nothing if a TicketsExceptHook is already installed...
        if is_tickets_excepthook(sys.excepthook):
            self.app.logger.info('Excepthook already installed...')
            return

        # Get the default excepthook (user or system default)
        if sys.excepthook is not sys.__excepthook__:
            self._default_excepthook = sys.excepthook
        else:
            self._default_excepthook = sys.__excepthook__

        self.app.logger.info(
            'Stored original excepthook: %r' % self._default_excepthook
        )

        # Install this object as the python excepthook
        sys.excepthook = self

    def _init_maya(self):
        '''Maya is a special case, it uses a custom excepthook mechanism.'''

        import maya.utils

        # Do nothing if a TicketsExceptHook is already installed...
        if is_tickets_excepthook(maya.utils.formatGuiException):
            self.app.logger.info('Excepthook already installed...')
            return

        # Get the default formatGuiException (user or system default)
        if maya.utils.formatGuiException is not maya.utils._formatGuiException:
            self._default_excepthook = maya.utils.formatGuiException
        else:
            self._default_excepthook = maya.utils._formatGuiException

        self.app.logger.info(
            'Stored original excepthook: %r' % self._default_excepthook
        )

        # Install this object as the maya formatGuiException hook
        maya.utils.formatGuiException = self

    def destroy(self):
        '''Remove the TicketsExceptHook.'''

        if not self.installed:
            return

        method = getattr(self, '_destroy_' + self._host)
        return method()

    def _destroy_python(self):
        '''Restore default sys.excepthook'''

        sys.excepthook = self._default_excepthook

    def _destroy_maya(self):
        '''Restore default maya.utils.formatGuiException'''

        import maya.utils
        maya.utils.formatGuiException = self._default_excepthook

    def __call__(self, typ, value, tb, *extra):
        '''Called when an unhandled exception occurs.'''

        result = self._default_excepthook(typ, value, tb, *extra)
        self.create_exception_ticket(typ, value, tb, self.confirm)
        return result

    def _get_current_context(self):
        engine = sgtk.platform.current_engine()
        return engine.context

    def create_exception_ticket(self, typ, value, tb, confirm=False):
        # Use events_hook.exception_filter to see if we should create a ticket
        ticket_should_be_created = self.app.execute_hook_method(
            'events_hook',
            'exception_filter',
            typ=typ,
            value=value,
            tb=tb,
        )
        if not ticket_should_be_created:
            return

        # Try to find a matching ticket for the traceback...
        error = self.format_exception(typ, value, tb)
        ticket = self.app.io.find_matching_error(error)
        if ticket:
            # Log message and update Ticket's count field
            self.app.logger.debug('Found matching Ticket #%s' % ticket['id'])
            count = (ticket['sg_count'] or 0) + 1
            self.app.io.update(ticket['id'], {'sg_count': count})
            return

        # Ticket fields
        fields = {
            'title': '[unhandled] %s - %s ' % (typ.__name__, value),
            'sg_ticket_type': 'Bug',
            'sg_priority': '3',
        }
        assignee = self.app.get_default_assignee()
        if assignee:
            fields['addressings_to'] = [assignee]

        # Show ticket dialog when excepthook_confirm is True
        # or confirm was explicitly passed.
        if confirm:
            message = (
                '<p style="color: #EB5757"><b>Unhandled Exception!</b></p>\n'
                '<p>Please write a brief description of what you were '
                'doing and submit a Ticket.</p>'
            )
            return self.app.show_tickets_submitter(
                title=fields['title'],
                type=fields['sg_ticket_type'],
                priority=fields['sg_priority'],
                error=error,
                context=self._get_current_context(),
                exc_info=(typ, value, tb),
                message=message,
                assignee=self.app.get_default_assignee(),
            )

        return self.app.create_ticket(
            fields,
            context=self.app.context,
            error=error,
            exc_info=(typ, value, tb),
        )

    def format_exception(self, typ, value, tb):
        return ''.join(traceback.format_exception(typ, value, tb)).rstrip('\n')

    def get_module_name(self, path):
        '''Get the dotted path to the specified python file.'''

        def _get_module_name(path):
            parts = [os.path.basename(path).rstrip('.py')]
            path = os.path.dirname(os.path.abspath(path))

            while True:
                if '__init__.py' in os.listdir(path):
                    parent_name = os.path.basename(path)
                    parts.append(parent_name)
                    path = os.path.dirname(path)
                else:
                    break

            return '.'.join(reversed(parts))

        try:
            return _get_module_name(path)
        except OSError:
            pass

    def iter_traceback(self, tb):
        '''Iterate over a traceback'''

        while tb:
            yield tb
            tb = tb.tb_next

    def last(self, iterable):
        '''Get the last item from an iterable'''

        return deque(iterable, maxlen=1)[0]

    def is_important_traceback(self, tb, includes=None, excludes=None):
        '''Is the traceback important?

        Called by the default events_hook.excepton_filter to determine if a
        Ticket should be created.
        '''

        tb = self.last(self.iter_traceback(tb))
        frame = tb.tb_frame
        frame_info = inspect.getframeinfo(frame)
        tb_module = self.get_module_name(frame_info.filename)

        if excludes:
            for pattern in excludes:
                if fnmatch.fnmatch(tb_module, pattern):
                    return False

        if includes:
            for pattern in includes:
                if fnmatch.fnmatch(tb_module, pattern):
                    return True

        return False

    def get_traceback_details(self, tb):
        '''Get valuable details from a Traceback.'''

        last_tb = self.last(self.iter_traceback(tb))
        frame = last_tb.tb_frame
        frame_info = inspect.getframeinfo(frame)
        module = self.get_module_name(frame_info.filename)
        thread = threading.current_thread()
        process = multiprocessing.current_process()

        return {
            'filename': frame_info.filename.replace('\\', '/'),
            'module': module,
            'thread': thread.ident,
            'threadName': thread.name,
            'process': process.pid,
            'processName': process.name,
            'lineno': frame_info.lineno,
            'funcName': frame_info.function,
            'culprit': module + '.' + frame_info.function,
        }


class TicketsIO(object):
    '''Responsible for all interactions with Shotgun Database.'''

    def __init__(self, app):
        self.app = app
        self.shotgun = app.shotgun

    def get_priority_values(self):
        schema = self.shotgun.schema_field_read('Ticket', 'sg_priority')
        props = schema['sg_priority']['properties']
        return props['valid_values']['value']

    def get_type_values(self):
        schema = self.shotgun.schema_field_read('Ticket', 'sg_ticket_type')
        props = schema['sg_ticket_type']['properties']
        return props['valid_values']['value']

    def find_matching_error(self, error):
        return self.shotgun.find_one(
            'Ticket',
            [['sg_error', 'is', error]],
            ['id', 'sg_count'],
        )

    def send_notification(self, ticket):
        '''Create a Note ensuring that users receive a notification in their
        Shotgun Inbox.'''

        assignees = ticket['addressings_to']
        created_by = ticket['created_by']
        subject = "%s's new Ticket #%s." % (
            ticket['created_by']['name'],
            ticket['id']
        )
        return self.shotgun.create(
            'Note',
            data={
                'addressings_to': ticket['addressings_to'],
                'user': ticket['created_by'],
                'subject': subject,
                'content': '%s' % self.app.get_ticket_url(ticket['id']),
                'project': ticket['project'],
                'note_links': [{'type': 'Ticket', 'id': ticket['id']}],
                'sg_note_type': 'Internal',
            },
        )

    def create(self, data):
        '''Create a Ticket.'''

        self.app.logger.debug(
            'Creating new Ticket: %s' % data.get('title', '')
        )
        return self.shotgun.create(
            'Ticket',
            data=data,
            return_fields=[
                'created_by',
                'created_at',
                'project',
                'title',
                'description',
                'addressings_to',
                'sg_context',
                'sg_error',
                'sg_type',
                'sg_priority',
                'sg_status_list',
            ]
        )

    def update(self, ticket_id, data):
        '''Update a Ticket.'''

        self.app.logger.debug(
            'Updating Ticket #%s: %s' % (ticket_id, data)
        )
        return self.shotgun.update('Ticket', ticket_id, data)

    def upload_attachments(self, ticket_id, attachments):
        '''Upload Ticket attachments.'''

        for i, attachment in enumerate(attachments):
            self.app.logger.debug(
                'Uploading attachment (%s of %s)' % (i + 1, len(attachments))
            )
            self.shotgun.upload(
                entity_type='Ticket',
                entity_id=ticket_id,
                path=attachment,
                field_name='attachments',
            )


def is_tickets_excepthook(obj):
    '''Check if an object is an instance or subclass of TicketsExceptHook.

    Used in TicketsExceptHook._init_<host> to ensure that we don't register
    more than one excepthook handler.
    '''

    return getattr(obj, '_is_tickets_excepthook', False)


def code_block(text):
    '''Wraps text in triple backticks making it a markdown codeblock.'''

    return '```{}```'.format(text)
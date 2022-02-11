import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class TicketsEventsHook(HookBaseClass):
    '''One hook to handle all tk-multi-tickets events.'''

    def exception_filter(self, typ, value, tb):
        '''Called when an unhandled exception occurs.

        This method filters unhandled exceptions returning True when an
        exception is deemed important enough to create a Ticket.

        Arguments:
            type: Exception class
            value: Exception instance
            traceback: Exception traceback

        Return:
            True if a Ticket should be created for the Exception
        '''

        # Always log unhandled exceptions....
        self.parent.engine.log_error('Unhandled Exception!')
        exc_message = ''.join(traceback.format_exception(typ, value, tb))
        self.parent.engine.log_error(exc_message)

        return self.parent.excepthook.is_important_traceback(
            tb=tb,
            includes=self.parent.excepthook.includes,
            excludes=self.parent.excepthook.excludes,
        )

    def before_create_ticket(self, fields, context, error=None, exc_info=None):
        '''Called before a Ticket is created.

        You can use this method to augment a Ticket's fields, context or
        customize it's error message.

        Arguments:
            fields (dict): Ticket field data
            context (dict): Ticket context dict
            error (None or str): Formated unhandled exception traceback
            exc_info (None or (typ, value, tb)): Unhandled exception info

        Return:
            Modified fields, context and error message.
        '''

        return fields, context, error

    def after_create_ticket(self, ticket):
        '''Called after a Ticket is created.

        Use this method if you'd like to perform a task with the new Ticket.

        Arguments:
            ticket (dict): Newly created Ticket entity including all fields.

        Return:
            None
        '''

        return NotImplemented

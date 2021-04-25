from django.utils.decorators import method_decorator
from viewflow import flow
from viewflow.base import this, Flow
from .models import WebinarProcess

def send_welcome_mail(*args, **kwargs):
    print(f"send_welcome_mail: ", args, kwargs)
    input("-- press return -- ")



def send_reminder_mail(*args, **kwargs):
    print(f"send_reminder_mail: ", args, kwargs)
    args[0].process.participated = bool(input("Participated ?"))
    args[0].process.save()


def send_replay_invitation(activation, *args, **kwargs):
    activation.prepare()
    if activation.process.participated:
        print(f"send_replay_invitation: ", args, kwargs)
        input("-- press return -- ")
        activation.done()
    return activation



class WebinarFlow(Flow):
    process_class = WebinarProcess

    start = flow.StartFunction(this.signup).Next(this.send_welcome)
    send_welcome = flow.Handler(send_welcome_mail).Next(this.send_reminder)
    send_reminder = flow.Handler(send_reminder_mail).Next(this.check_participation)
    check_participation = flow.If(lambda x: x.process.participated).Then(
            this.end
    ).Else(
            this.send_replay_invitation
    )
    send_replay_invitation = flow.Function(send_replay_invitation).Next(this.end)
    end = flow.End()

    @method_decorator(flow.flow_start_func)
    def signup(self, activation, session, **kwargs):
        activation.prepare()
        activation.process.session = session
        activation.process.mail_id = 1
        activation.process.save()
        print(activation, kwargs)
        activation.done()
        return activation

flow.Next.ready()
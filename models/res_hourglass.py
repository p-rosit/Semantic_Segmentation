import importlib
import torch
from torch import nn

class Network(nn.Module):
    def __init__(self, config):
      super(Network, self).__init__()
      # Network libraries chosen in config
      pre_network  = importlib.import_module('models.prenet.' + config['network']['prenet']).Network
      base_network = importlib.import_module('models.base.' + config['network']['base']).Network
      
      # Network which distills the information in the image
      self.prenet = pre_network(config)

      # Parameters from the prenet and config
      self.dim       = config['oup_dim']
      self.num_class = config['num_class']
      self.max_stack = config['max_stack']

      # Hourglass modules
      self.hgs = nn.ModuleList( [nn.Sequential(base_network(config)) for i in range(self.max_stack)])
        
      # Convolutional layers needed for classification and making sure everything has the correct number of channels
      self.classifier   = nn.Conv2d(config['f'], config['num_class'], 1)
      self.declassifier = nn.Conv2d(config['num_class'], config['f'], 1)

      # Residual connection alpha and activation function
      self.alpha = nn.Parameter(torch.zeros(config['max_stack']-1))
      self.beta  = nn.Parameter(torch.zeros(config['max_stack']-1))
      self.ReLU  = nn.LeakyReLU(inplace=True)
       
      # Normalization layers 
      if   config['normalization'] == 'batch':
        self.bn1 = nn.BatchNorm2d(config['num_class'])
        self.bn2 = nn.BatchNorm2d(config['f'])
      elif config['normalization'] == 'layerHW':
        self.bn1 = nn.LayerNorm([config['oup_dim'][0], config['oup_dim'][1]])
        self.bn2 = nn.LayerNorm([config['oup_dim'][0], config['oup_dim'][1]])
      elif config['normalization'] == 'layerCHW':
        self.bn1 = nn.LayerNorm([config['num_class'], config['oup_dim'][0], config['oup_dim'][1]])
        self.bn2 = nn.LayerNorm([config['f'], config['oup_dim'][0], config['oup_dim'][1]])
      else:
        raise Exception('Not a valid normalization')

    def forward(self, x):
      out = torch.empty(self.max_stack, x.shape[0], self.num_class, self.dim[0], self.dim[1]).to(x.device)
      
      # Distill input image
      hidden = self.prenet(x)
      
      for i in range(self.max_stack):
        # Improve hidden state
        if i == 0:
          prev_hidden = hidden.clone()
          hidden = self.hgs[i](hidden)
        else:
          temp_prev_hidden = hidden.clone()
          hidden = self.hgs[i](self.beta[i-1] * residual + self.alpha[i-1] * hidden + prev_hidden)
          prev_hidden = temp_prev_hidden
        
        # Compute predicted segmentation
        segmentation = self.ReLU(self.bn1(self.classifier(hidden)))
        out[i]       = segmentation
        if i < self.max_stack - 1:
          residual   = self.ReLU(self.bn2(self.declassifier(segmentation)))
        
      out = out.swapaxes(0, 1)
        
      return out
